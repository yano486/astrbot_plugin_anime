from __future__ import annotations

import asyncio
from datetime import date
from typing import Any
from urllib.parse import urlsplit, urlencode

from ..diagnostics import get_plugin_logger
from .base import SourceAdapter, SourceResult
from .helpers import ADAPTATION_TYPE_ORDER, adaptation_types, make_schedule, season_year_month
from ..models import SourceRecord


logger = get_plugin_logger()


def normalize_proxy_url(value: Any) -> str | None:
    value = str(value or "").strip()
    if not value:
        return None
    if "://" not in value:
        value = f"http://{value}"
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.port is None:
        raise ValueError("Bangumi proxy must be an HTTP URL with a port")
    return value.rstrip("/")


def _region(tags: list[dict[str, Any]]) -> str:
    names = {str(tag.get("name", "")) for tag in tags}
    if "日本" in names:
        return "jp"
    if names & {"美国", "欧美", "中国", "大陆", "韩国"}:
        return "foreign"
    return "unknown"


def parse_bangumi_payload(
    payload: dict[str, Any] | list[dict[str, Any]],
    source_url: str = "",
    exclude_r18: bool = False,
) -> list[SourceRecord]:
    values = payload.get("data", []) if isinstance(payload, dict) else payload
    records: list[SourceRecord] = []
    for item in values or []:
        if not isinstance(item, dict) or item.get("type") not in (None, 2):
            continue
        raw_meta = item.get("meta_tags") or []
        tags_list = item.get("tags", []) or []
        if raw_meta and isinstance(raw_meta[0], dict):
            tags = [str(tag.get("name", "")) for tag in raw_meta]
        elif raw_meta:
            tags = [str(tag) for tag in raw_meta]
        else:
            tags = [str(tag.get("name", "")) for tag in tags_list if isinstance(tag, dict)]
        adaptation_tags = tags + [str(tag.get("name", "")) for tag in tags_list if isinstance(tag, dict)]
        if exclude_r18 and any(
            value.casefold() in {"r18", "18禁", "成人"} or "r18" in value.casefold()
            for value in tags
        ):
            continue
        item_type = str(item.get("platform", "unknown")).lower()
        if item_type == "tv":
            item_type = "tv"
        elif item_type == "web":
            item_type = "web"
        elif "ova" in item_type:
            item_type = "ova"
        elif "剧场" in item_type or "movie" in item_type:
            item_type = "movie"
        else:
            item_type = "unknown"
        records.append(
            SourceRecord(
                source="bangumi",
                title=str(item.get("name", "")),
                title_cn=str(item.get("name_cn", "")),
                bangumi_id=int(item["id"]) if str(item.get("id", "")).isdigit() else None,
                aliases=[str(item.get("name", "")), str(item.get("name_cn", ""))],
                season=str(item.get("date", ""))[:7],
                item_type=item_type,
                region=(
                    "jp" if "日本" in tags
                    else "foreign" if set(tags) & {"美国", "欧美", "中国", "大陆", "韩国"}
                    else _region([tag for tag in tags_list if isinstance(tag, dict)])
                ),
                genres=tags,
                adaptation_types=adaptation_types(adaptation_tags),
                cover_url=str((item.get("images") or {}).get("large", "")),
                detail_url=str(item.get("url", "")),
                source_url=source_url,
                release_date=str(item.get("date", ""))[:10],
            )
        )
    return records


class BangumiAdapter(SourceAdapter):
    name = "bangumi"
    base_url = "https://api.bgm.tv/v0/subjects"

    def __init__(self, session: Any = None, api_token: str = "", proxy_url: Any = ""):
        super().__init__(session)
        self.api_token = api_token.strip()
        self.exclude_r18 = False
        self.proxy_url = normalize_proxy_url(proxy_url)

    def _headers(self) -> dict[str, str]:
        headers = {"User-Agent": "yano486/astrbot_plugin_anime/0.2 (https://github.com/yano486/astrbot_plugin_anime)"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers

    async def fetch_month(self, year: int, month: int, season: str | None = None) -> SourceResult:
        if self.session is None:
            return SourceResult(self.name, status="error", error="session unavailable", source_url=self.base_url)
        try:
            records: list[SourceRecord] = []
            offset = 0
            total = None
            while total is None or offset < min(total, 500):
                query = urlencode({"type": 2, "year": year, "month": month, "sort": "date", "limit": 100, "offset": offset})
                url = f"{self.base_url}?{query}"
                request_kwargs = {"proxy": self.proxy_url} if self.proxy_url else {}
                logger.info("[anime] Bangumi 请求 %s%s", url, "（使用代理）" if self.proxy_url else "")
                async with self.session.get(url, headers=self._headers(), **request_kwargs) as response:
                    if response.status == 404:
                        return SourceResult(self.name, status="empty", source_url=url)
                    if response.status != 200:
                        return SourceResult(self.name, status="error", error=f"HTTP {response.status}", source_url=url)
                    payload = await response.json()
                batch = parse_bangumi_payload(payload, url, self.exclude_r18)
                for record in batch:
                    record.season = season or f"{year}-{month:02d}"
                records.extend(batch)
                total = int(payload.get("total", len(records))) if isinstance(payload, dict) else len(records)
                offset += 100
                if not batch:
                    break
            return SourceResult(self.name, records, self.base_url, "ok" if records else "empty")
        except Exception as exc:
            logger.error("[anime] Bangumi 请求失败 %s-%02d：%s: %s", year, month, type(exc).__name__, exc)
            return SourceResult(self.name, status="error", error=f"{type(exc).__name__}: {exc}", source_url=self.base_url)

    async def fetch(self, season: str) -> SourceResult:
        year, month = season_year_month(season)
        semaphore = asyncio.Semaphore(2)

        async def fetch_adjacent(offset: int) -> tuple[str, SourceResult]:
            month_index = year * 12 + month - 1 + offset
            current_year, zero_month = divmod(month_index, 12)
            current_month = zero_month + 1
            async with semaphore:
                return f"{current_year}-{current_month:02d}", await self.fetch_month(current_year, current_month, season)

        # Include the preceding month so a show that started just before the
        # quarter is still visible while it remains part of this season's list.
        results = await asyncio.gather(*(fetch_adjacent(offset) for offset in range(-1, 3)))
        records: list[SourceRecord] = []
        statuses: dict[str, str] = {}
        for period, result in results:
            statuses[period] = result.error if result.status == "error" else result.status
            if result.status == "ok":
                records.extend(result.records)
        if not records and any(value not in {"ok", "empty"} for value in statuses.values()):
            return SourceResult(self.name, status="error", error=f"monthly query failures: {statuses}", source_url=self.base_url)
        return SourceResult(self.name, records, self.base_url, "ok" if records else "empty")

    async def fetch_movies(self, today: date) -> SourceResult:
        records: list[SourceRecord] = []
        years = [today.year] + ([today.year + 1] if today.month == 12 else [])
        statuses: dict[str, str] = {}
        semaphore = asyncio.Semaphore(2)

        async def fetch_movie_month(year: int, month: int):
            async with semaphore:
                return year, month, await self.fetch_month(year, month)

        results = await asyncio.gather(*(fetch_movie_month(year, month) for year in years for month in range(1, 13)))
        for year, month, result in results:
            statuses[f"{year}-{month:02d}"] = result.error if result.status == "error" else result.status
            if result.status == "ok":
                records.extend(record for record in result.records if record.item_type in ("movie", "ova"))
        failures = {month: error for month, error in statuses.items() if error != "ok"}
        if not records:
            return SourceResult(self.name, status="error", error=f"no movie/OVA records returned; month failures: {failures}", source_url=self.base_url)
        return SourceResult(self.name, records, self.base_url, "ok", f"partial month failures: {failures}" if failures else "")

