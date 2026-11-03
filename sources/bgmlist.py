from __future__ import annotations

from typing import Any
from datetime import datetime, timezone

from .base import SourceAdapter, SourceResult
from .helpers import make_schedule
from ..models import SourceRecord


def _schedule_from_item(item: dict[str, Any]) -> list:
    broadcast = str(item.get("broadcast", ""))
    begin = broadcast.split("/")[1] if "/" in broadcast and len(broadcast.split("/")) > 1 else str(item.get("begin", ""))
    try:
        dt = datetime.fromisoformat(begin.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return []
    # bangumi-data timestamps are UTC; convert to Japan before extracting weekday/time.
    from zoneinfo import ZoneInfo

    local = dt.astimezone(ZoneInfo("Asia/Tokyo"))
    schedule = make_schedule("bgmlist", local.isoweekday(), local.strftime("%H:%M"), start_date=local.date().isoformat())
    if schedule and "/P" in broadcast:
        period = broadcast.rsplit("/P", 1)[-1].rstrip("D")
        try:
            schedule.interval_days = int(period or 7)
        except ValueError:
            pass
    return [schedule] if schedule else []


def parse_bgmlist_payload(payload: dict[str, Any] | list[dict[str, Any]], source_url: str = "", season: str = "") -> list[SourceRecord]:
    records: list[SourceRecord] = []
    values = payload.get("items", []) if isinstance(payload, dict) else payload
    for item in values or []:
        if not isinstance(item, dict):
            continue
        bangumi_id = None
        for site in item.get("sites", []):
            if isinstance(site, dict) and site.get("site") == "bangumi" and str(site.get("id", "")).isdigit():
                bangumi_id = int(site["id"])
                break
        if bangumi_id is None:
            continue
        records.append(
            SourceRecord(
                source="bgmlist",
                title=str(item.get("title", "")),
                title_cn=str(((item.get("titleTranslate") or {}).get("zh-Hans") or [""])[0]),
                bangumi_id=bangumi_id,
                aliases=list((item.get("titleTranslate") or {}).get("zh-Hans", [])),
                item_type=str(item.get("type", "unknown")),
                region="jp" if item.get("lang") == "ja" else "unknown",
                schedules=_schedule_from_item(item),
                source_url=source_url,
                season=season,
            )
        )
    return records


class BgmlistAdapter(SourceAdapter):
    name = "bgmlist"
    url = "https://bgmlist.com/api/v1/bangumi/onair"

    async def fetch(self, season: str) -> SourceResult:
        year, month = int(season[:4]), int(season[-2:])
        if self.session is None:
            return SourceResult(self.name, status="error", error="session unavailable")
        records = []
        urls = []
        try:
            # Keep adjacent-month broadcasts in the selected quarter's catalog.
            for offset in range(-1, 3):
                month_index = year * 12 + month - 1 + offset
                current_year, zero_month = divmod(month_index, 12)
                current_month = zero_month + 1
                url = f"https://raw.githubusercontent.com/bangumi-data/bangumi-data/master/data/items/{current_year}/{current_month:02d}.json"
                urls.append(url)
                async with self.session.get(url, headers={"User-Agent": "astrbot_plugin_anime/0.1"}) as response:
                    if response.status == 404:
                        continue
                    if response.status != 200:
                        return SourceResult(self.name, status="error", error=f"HTTP {response.status}", source_url=url)
                    records.extend(parse_bgmlist_payload(await response.json(content_type=None), url, season))
            return SourceResult(self.name, records, ",".join(urls), "ok" if records else "error", "" if records else "no quarter data")
        except Exception as exc:
            return SourceResult(self.name, status="error", error=f"{type(exc).__name__}: {exc}", source_url=",".join(urls))

