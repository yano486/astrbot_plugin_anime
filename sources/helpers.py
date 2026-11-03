from __future__ import annotations

import re
from datetime import datetime

from ..models import Schedule
from ..time_utils import parse_broadcast_clock

WEEKDAY_MAP = {
    "周一": 1,
    "星期一": 1,
    "一": 1,
    "月": 1,
    "周二": 2,
    "星期二": 2,
    "二": 2,
    "火": 2,
    "周三": 3,
    "星期三": 3,
    "三": 3,
    "水": 3,
    "周四": 4,
    "星期四": 4,
    "四": 4,
    "木": 4,
    "周五": 5,
    "星期五": 5,
    "五": 5,
    "金": 5,
    "周六": 6,
    "星期六": 6,
    "六": 6,
    "土": 6,
    "周日": 7,
    "星期日": 7,
    "星期天": 7,
    "日": 7,
}


def weekday_number(value: str) -> int | None:
    value = (value or "").strip()
    for key, number in WEEKDAY_MAP.items():
        if key in value:
            return number
    return None


def make_schedule(
    source: str,
    weekday: int | None,
    raw_time: str,
    source_url: str = "",
    start_date: str = "",
    interval_days: int = 7,
) -> Schedule | None:
    clock = parse_broadcast_clock(raw_time)
    if weekday is None or clock is None:
        return None
    hour, minute = clock
    return Schedule(
        weekday=weekday,
        hour=hour,
        minute=minute,
        raw_time=raw_time,
        source=source,
        source_url=source_url,
        start_date=start_date,
        interval_days=interval_days,
    )


def parse_iso_time(value: str) -> tuple[int, int, int, str] | None:
    if not value:
        return None
    try:
        text = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    local = dt.astimezone()
    return local.isoweekday(), local.hour, local.minute, local.date().isoformat()


def season_year_month(season: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d{4})[-/]?(\d{2})", season)
    if not match:
        now = datetime.now()
        return now.year, ((now.month - 1) // 3) * 3 + 1
    return int(match.group(1)), int(match.group(2))


def normalize_start_date(value: str, season: str = "") -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        pass
    match = re.search(r"(\d{1,2})/(\d{1,2})", raw)
    if not match:
        return ""
    year, season_month = season_year_month(season)
    month, day = int(match.group(1)), int(match.group(2))
    if season_month == 1 and month >= 10:
        year -= 1
    try:
        return datetime(year, month, day).date().isoformat()
    except ValueError:
        return ""

