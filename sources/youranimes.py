from __future__ import annotations

import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from .base import SourceAdapter, SourceResult
from .helpers import make_schedule, weekday_number
from ..models import SourceRecord


def _walk_json(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _extract_bangumi_id(links) -> int | None:
    if isinstance(links, str):
        links = [links]
    for link in links or []:
        match = re.search(r"bangumi\.tv/subject/(\d+)", str(link))
        if match:
            return int(match.group(1))
    return None


def parse_youranimes_html(html: str, season: str = "", source_url: str = "") -> list[SourceRecord]:
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    records: list[SourceRecord] = []
    seen = set()
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            payload = json.loads(script.string or script.get_text())
        except (TypeError, ValueError):
            continue
        for item in _walk_json(payload):
            item_type = item.get("@type", [])
            if isinstance(item_type, str):
                item_type = [item_type]
            if not any(value in ("TVSeries", "Movie", "CreativeWorkSeries") for value in item_type):
                continue
            start = item.get("datePublished") or item.get("startDate") or ""
            try:
                moment = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
                moment = moment.replace(tzinfo=ZoneInfo("Asia/Tokyo")) if moment.tzinfo is None else moment.astimezone(ZoneInfo("Asia/Tokyo"))
            except ValueError:
                continue
            title = str(item.get("name", "")).strip()
            if not title:
                continue
            aliases = item.get("alternateName", [])
            aliases = [aliases] if isinstance(aliases, str) else list(aliases or [])
            detail_url = str(item.get("url", ""))
            key = detail_url or title
            if key in seen:
                continue
            seen.add(key)
            studio = item.get("productionCompany", "")
            if isinstance(studio, list):
                studio = ", ".join(str(value.get("name", "")) for value in studio if isinstance(value, dict))
            elif isinstance(studio, dict):
                studio = str(studio.get("name", ""))
            count = item.get("numberOfEpisodes")
            records.append(SourceRecord(
                source="youranimes",
                title=str((aliases or [title])[0]),
                title_cn=next((str(alias) for alias in aliases if re.search(r"[\u4e00-\u9fff]", str(alias))), title),
                bangumi_id=_extract_bangumi_id(item.get("sameAs", [])),
                aliases=[title, *aliases],
                season=season or moment.strftime("%Y-%m"),
                season_role="continuing" if season and moment.strftime("%Y-%m") != season else "new",
                item_type="movie" if "Movie" in item_type else "tv",
                region="jp",
                genres=[str(value) for value in (item.get("genre", []) if isinstance(item.get("genre"), list) else [item.get("genre")]) if value],
                cover_url=str(item.get("image", "")),
                detail_url=detail_url,
                schedules=[make_schedule("youranimes", moment.isoweekday(), moment.strftime("%H:%M"), source_url, moment.date().isoformat())],
                source_url=source_url,
                studio=str(studio),
                episode_count=int(count) if str(count or "").isdigit() else None,
                release_date=moment.date().isoformat(),
            ))
    if records:
        return records
    for block in soup.select("article, [data-anime-id], .anime-card, .anime-item"):
        text = block.get_text(" ", strip=True)
        clock_match = re.search(r"(?:星期|周)[一二三四五六日天]\s*/?\s*(\d{1,2}:\d{2})", text)
        if not clock_match:
            continue
        weekday = weekday_number(text)
        title_node = block.select_one("h2, h3, h4, .title, [class*=title]")
        title = title_node.get_text(" ", strip=True) if title_node else ""
        if not title or weekday is None:
            continue
        raw_time = clock_match.group(1)
        role = "continuing" if "跨季" in text or "續播" in text or "续播" in text else "unknown"
        schedule = make_schedule("youranimes", weekday, raw_time, source_url)
        records.append(
            SourceRecord(
                source="youranimes",
                title=title,
                season=season,
                season_role=role,
                schedules=[schedule] if schedule else [],
                source_url=source_url,
            )
        )
    return records


class YourAnimesAdapter(SourceAdapter):
    name = "youranimes"
    base_url = "https://youranimes.tw/bangumi/"

    async def fetch(self, season: str) -> SourceResult:
        season_path = season.replace("-", "")
        url = f"https://youranimes.tw/bangumi/{season_path}"
        if self.session is None:
            return SourceResult(self.name, status="error", error="session unavailable", source_url=url)
        try:
            async with self.session.get(url, headers={"User-Agent": "astrbot_plugin_anime/0.1"}) as response:
                if response.status != 200:
                    return SourceResult(self.name, status="error", error=f"HTTP {response.status}", source_url=url)
                records = parse_youranimes_html(await response.text(), season, url)
                return SourceResult(self.name, records, url, "ok" if records else "error", "" if records else "schedule structure not found")
        except Exception as exc:
            return SourceResult(self.name, status="error", error=str(exc), source_url=url)

