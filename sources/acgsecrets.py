from __future__ import annotations

import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from .base import SourceAdapter, SourceResult
from .helpers import make_schedule, weekday_number
from ..core.models import SourceRecord


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


def _record_from_json(item: dict, source_url: str) -> SourceRecord | None:
    item_type = item.get("@type", [])
    if isinstance(item_type, str):
        item_type = [item_type]
    if not any(value in ("TVSeries", "Movie", "CreativeWorkSeries") for value in item_type):
        return None
    start = item.get("startDate") or item.get("datePublished") or ""
    try:
        moment = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
        moment = moment.replace(tzinfo=ZoneInfo("Asia/Tokyo")) if moment.tzinfo is None else moment.astimezone(ZoneInfo("Asia/Tokyo"))
    except ValueError:
        return None
    title = str(item.get("name", "")).strip()
    if not title:
        return None
    aliases = item.get("alternateName", [])
    aliases = [aliases] if isinstance(aliases, str) else list(aliases or [])
    studio = item.get("productionCompany", "")
    if isinstance(studio, dict):
        studio = str(studio.get("name", ""))
    elif isinstance(studio, list):
        studio = ", ".join(str(value.get("name", "")) for value in studio if isinstance(value, dict))
    count = item.get("numberOfEpisodes")
    return SourceRecord(
        source="acgsecrets",
        title=str((aliases or [title])[0]),
        title_cn=title,
        bangumi_id=_extract_bangumi_id(item.get("sameAs", [])),
        aliases=[title, *aliases],
        season=moment.strftime("%Y-%m"),
        item_type="movie" if "Movie" in item_type else "tv",
        region="jp",
        genres=[str(value) for value in (item.get("genre", []) if isinstance(item.get("genre"), list) else [item.get("genre")]) if value],
        cover_url=str(item.get("image", "")),
        detail_url=str(item.get("url", "")),
        schedules=[make_schedule("acgsecrets", moment.isoweekday(), moment.strftime("%H:%M"), source_url, moment.date().isoformat())],
        source_url=source_url,
        studio=str(studio),
        episode_count=int(count) if str(count or "").isdigit() else None,
        release_date=moment.date().isoformat(),
    )


def parse_acgsecrets_html(html: str, season: str = "", source_url: str = "") -> list[SourceRecord]:
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
            record = _record_from_json(item, source_url)
            if record and record.detail_url not in seen:
                if season:
                    record.season = season
                    record.season_role = "continuing" if record.schedules and record.schedules[0].start_date[:7] != season else "new"
                seen.add(record.detail_url)
                records.append(record)
    if records:
        return records

    blocks = soup.select(".acgs-anime-block, .acgs-anime-icon")
    for block in blocks:
        text = block.get_text(" ", strip=True)
        clock_match = re.search(r"\b\d{1,2}:\d{2}\b", text)
        weekday_match = re.search(r"(?:星期|周)([一二三四五六日天])", text)
        weekday = weekday_number(weekday_match.group(0) if weekday_match else text)
        title_node = block.select_one(".anime_title, .title, h2, h3")
        title = title_node.get_text(" ", strip=True) if title_node else ""
        if not title or weekday is None or not clock_match:
            continue
        schedule = make_schedule("acgsecrets", weekday, clock_match.group(0), source_url)
        records.append(SourceRecord(source="acgsecrets", title=title, season=season, region="jp", schedules=[schedule] if schedule else [], source_url=source_url))
    return records


class AcgSecretsAdapter(SourceAdapter):
    name = "acgsecrets"
    base_url = "https://acgsecrets.hk/bangumi/"

    async def fetch(self, season: str) -> SourceResult:
        url = f"{self.base_url}{season.replace('-', '')}/"
        if self.session is None:
            return SourceResult(self.name, status="error", error="session unavailable", source_url=url)
        try:
            async with self.session.get(url, headers={"User-Agent": "astrbot_plugin_anime/0.1"}) as response:
                if response.status != 200:
                    return SourceResult(self.name, status="error", error=f"HTTP {response.status}", source_url=url)
                records = parse_acgsecrets_html(await response.text(), season, url)
                return SourceResult(self.name, records, url, "ok" if records else "error", "" if records else "schedule structure not found")
        except Exception as exc:
            return SourceResult(self.name, status="error", error=str(exc), source_url=url)
