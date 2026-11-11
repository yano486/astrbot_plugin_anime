from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
import re
import time as clock
from stat import S_ISREG
from typing import Iterable
from zoneinfo import ZoneInfo

from ..core.models import AnimeItem, Schedule
from ..core.time_utils import BJ, JST
from .card_layouts import render_notice, render_table


_GENERATED_TABLE_NAME = re.compile(r"[0-9a-f]{32}\.png\Z")


@dataclass(frozen=True)
class Airing:
    item: AnimeItem
    schedule: Schedule | None
    at: datetime


def cleanup_generated_tables(
    directory: Path,
    *,
    now: float | None = None,
    retention_seconds: float = 7 * 86400,
) -> int:
    root = Path(directory)
    if root.is_symlink() or not root.is_dir():
        return 0
    cutoff = (clock.time() if now is None else now) - max(0, retention_seconds)
    removed = 0
    for path in root.iterdir():
        if not _GENERATED_TABLE_NAME.fullmatch(path.name):
            continue
        try:
            file_stat = path.lstat()
        except FileNotFoundError:
            continue
        if S_ISREG(file_stat.st_mode) and file_stat.st_mtime < cutoff:
            path.unlink()
            removed += 1
    return removed


def _first_occurrence(schedule: Schedule) -> datetime | None:
    if not schedule.start_date:
        return None
    try:
        day = date.fromisoformat(schedule.start_date[:10])
    except ValueError:
        return None
    offset, minutes = divmod(schedule.hour * 60 + schedule.minute, 24 * 60)
    local = datetime.combine(day + timedelta(days=offset), time(minutes // 60, minutes % 60), JST)
    return local.astimezone(BJ)


def airings_between(items: Iterable[AnimeItem], start: datetime, end: datetime) -> list[Airing]:
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start and end must be timezone-aware")
    start, end = start.astimezone(BJ), end.astimezone(BJ)
    rows: dict[tuple[str, datetime], Airing] = {}
    for item in items:
        if item.item_type in ("movie", "ova"):
            continue
        for schedule in item.schedules:
            first = _first_occurrence(schedule)
            if first is None:
                # Date-less weekly records can still be placed into the requested calendar window.
                local_start = start.astimezone(JST)
                day_offset = (schedule.weekday - local_start.isoweekday()) % 7
                candidate_day = local_start.date() + timedelta(days=day_offset)
                local_minutes = (schedule.hour % 24) * 60 + schedule.minute
                jst_dt = datetime.combine(candidate_day, time(local_minutes // 60, local_minutes % 60), JST)
                if schedule.hour >= 24:
                    jst_dt += timedelta(days=schedule.hour // 24)
                first = jst_dt.astimezone(BJ)
                interval = max(1, schedule.interval_days or 7)
                while first < start:
                    first += timedelta(days=interval)
                candidate = first
                while candidate < end:
                    rows[(item.key, candidate)] = Airing(item, schedule, candidate)
                    candidate += timedelta(days=interval)
                continue
            interval = max(1, schedule.interval_days or 7)
            candidate = first
            if candidate < start:
                steps = max(0, (start.date() - candidate.date()).days // interval)
                candidate += timedelta(days=steps * interval)
                while candidate < start:
                    candidate += timedelta(days=interval)
            while candidate < end:
                rows[(item.key, candidate)] = Airing(item, schedule, candidate)
                candidate += timedelta(days=interval)
    return sorted(rows.values(), key=lambda row: (row.at, row.item.title_cn or row.item.title))


def upcoming_movies(items: Iterable[AnimeItem], today: date) -> list[Airing]:
    last_year = today.year + (1 if today.month == 12 else 0)
    rows = []
    for item in items:
        if item.item_type not in ("movie", "ova") or item.region not in ("jp", "mixed") or not item.release_date:
            continue
        try:
            release = date.fromisoformat(item.release_date[:10])
        except ValueError:
            continue
        if today <= release and release.year <= last_year:
            rows.append(Airing(item, None, datetime.combine(release, time.min, BJ)))
    return sorted(rows, key=lambda row: (row.at, row.item.title_cn or row.item.title))


def render_airings_image(title: str, rows: list[Airing], output: Path, display_timezone: str = "Asia/Shanghai", **options) -> Path:
    return render_table(title, rows, output, display_timezone, **options)


def render_weekly_image(title: str, rows: list[Airing], output: Path, display_timezone: str = "Asia/Shanghai", **options) -> Path:
    return render_table(title, rows, output, display_timezone, weekly=True, **options)


def render_subscription_table_image(title: str, rows: list[Airing], output: Path, display_timezone: str = "Asia/Shanghai", *, kind: str = "daily", **options) -> Path:
    if kind not in {"daily", "weekly"}:
        raise ValueError("kind must be daily or weekly")
    return render_table(title, rows, output, display_timezone, weekly=kind == "weekly", **options)


def render_notification_card(item: AnimeItem, mode: str, output: Path, display_timezone: str = "Asia/Shanghai", **options) -> Path:
    return render_notice(item, mode, output, display_timezone, **options)
