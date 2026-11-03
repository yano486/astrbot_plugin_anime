from __future__ import annotations

from datetime import date
from typing import Any
from urllib.parse import urlencode

from .base import SourceAdapter, SourceResult
from .helpers import make_schedule, season_year_month
from ..models import SourceRecord


def _region(tags: list[dict[str, Any]]) -> str:
    names = {str(tag.get("name", "")) for tag in tags}
    if "日本" in names:
        return "jp"
    if names & {"美国", "欧美", "中国", "大陆", "韩国"}:
        return "foreign"
    return "unknown"


def parse_bangumi_payload(payload: dict[str, Any] | list[dict[str, Any]], source_url: str = "") -> list[SourceRecord]:
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
                async with self.session.get(url, headers={"User-Agent": "yano486/astrbot_plugin_anime/0.1 (https://github.com/yano486/astrbot_plugin_anime)"}) as response:
                    if response.status != 200:
                        return SourceResult(self.name, status="error", error=f"HTTP {response.status}", source_url=url)
                    payload = await response.json()
                batch = parse_bangumi_payload(payload, url)
                for record in batch:
                    record.season = season or f"{year}-{month:02d}"
                records.extend(batch)
                total = int(payload.get("total", len(records))) if isinstance(payload, dict) else len(records)
                offset += 100
                if not batch:
                    break
            return SourceResult(self.name, records, self.base_url)
        except Exception as exc:
            return SourceResult(self.name, status="error", error=f"{type(exc).__name__}: {exc}", source_url=self.base_url)

    async def fetch(self, season: str) -> SourceResult:
        year, month = season_year_month(season)
        records: list[SourceRecord] = []
        statuses: dict[str, str] = {}
        for offset in range(3):
            month_index = year * 12 + month - 1 + offset
            current_year, zero_month = divmod(month_index, 12)
            current_month = zero_month + 1
            result = await self.fetch_month(current_year, current_month, season)
            statuses[f"{current_year}-{current_month:02d}"] = result.error if result.status == "error" else result.status
            if result.status == "ok":
                records.extend(result.records)
        if not records and any(value == "error" for value in statuses.values()):
            return SourceResult(self.name, status="error", error=f"monthly query failures: {statuses}", source_url=self.base_url)
        return SourceResult(self.name, records, self.base_url, "ok" if records else "error", "" if records else f"no quarter data: {statuses}")

    async def fetch_movies(self, today: date, months: int = 3) -> SourceResult:
        records: list[SourceRecord] = []
        for offset in range(months + 1):
            month_index = today.year * 12 + today.month - 1 + offset
            year, zero_month = divmod(month_index, 12)
            result = await self.fetch_month(year, zero_month + 1)
            if result.status == "ok":
                records.extend(record for record in result.records if record.item_type in ("movie", "ova"))
        if not records:
            return SourceResult(self.name, status="error", error="no upcoming movie catalog returned")
        return SourceResult(self.name, records, self.base_url)

