from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from .base import SourceAdapter, SourceResult
from .helpers import make_schedule, normalize_start_date, weekday_number, season_year_month
from ..models import SourceRecord


def _title_from_card(card: Any) -> str:
    title = card.find(class_=re.compile(r"date_title")) if card else None
    if title:
        return re.sub(r"\s+", " ", title.get_text(" ", strip=True))
    return ""


def parse_yuc_html(html: str, season: str = "", source_url: str = "") -> list[SourceRecord]:
    if not html or "date2" not in html or "div_date" not in html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    records: list[SourceRecord] = []
    headers = soup.find_all(class_="date2")
    for header in headers:
        weekday = weekday_number(header.get_text(" ", strip=True))
        if weekday is None:
            continue
        cards = []
        for element in header.find_all_next():
            classes = element.get("class", [])
            if "date2" in classes:
                break
            if any(re.match(r"^div_date", name) for name in classes):
                cards.append(element)
        for card in cards:
            title_node = card.find_next(class_=re.compile(r"^date_title"))
            title = re.sub(r"\s+", " ", title_node.get_text(" ", strip=True)) if title_node else ""
            if not title:
                continue
            time_node = card.find(class_="imgtext4")
            date_node = card.find(class_=re.compile(r"^imgep2$")) or card.find(class_=re.compile(r"^imgep$"))
            raw_time = time_node.get_text(" ", strip=True) if time_node else ""
            start_date = normalize_start_date(date_node.get_text(" ", strip=True) if date_node else "", season)
            schedule = make_schedule("yuc", weekday, raw_time, source_url, start_date)
            records.append(
                SourceRecord(
                    source="yuc",
                    title=title,
                    season=season,
                    region="unknown",
                    schedules=[schedule] if schedule else [],
                    source_url=source_url,
                )
            )
    return records


class YucAdapter(SourceAdapter):
    name = "yuc"

    async def fetch(self, season: str) -> SourceResult:
        year, month = season_year_month(season)
        url = f"https://yuc.wiki/{year}{month:02d}/"
        if self.session is None:
            return SourceResult(self.name, status="error", error="session unavailable", source_url=url)
        try:
            async with self.session.get(url, headers={"User-Agent": "astrbot_plugin_anime/0.1"}) as response:
                if response.status != 200:
                    return SourceResult(self.name, status="error", error=f"HTTP {response.status}", source_url=url)
                html = await response.text()
                records = parse_yuc_html(html, season, url)
                return SourceResult(self.name, records, url, "ok" if records else "error", "" if records else "schedule structure not found")
        except Exception as exc:
            return SourceResult(self.name, status="error", error=str(exc), source_url=url)

