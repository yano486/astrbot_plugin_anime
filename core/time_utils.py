from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import re
from zoneinfo import ZoneInfo


BJ = ZoneInfo("Asia/Shanghai")
JST = ZoneInfo("Asia/Tokyo")


def parse_broadcast_clock(raw: str) -> tuple[int, int] | None:
    if not raw:
        return None
    match = re.search(r"(\d{1,2}):(\d{2})", raw.strip())
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 29 or minute > 59:
        return None
    return hour, minute


def jst_weekday_time_to_beijing(
    weekday: int, hour: int, minute: int
) -> tuple[int, int, int, int]:
    if weekday not in range(1, 8) or hour not in range(0, 30) or minute not in range(0, 60):
        raise ValueError("invalid weekday or clock")
    total_minutes = hour * 60 + minute - 60
    day_delta, bj_minutes = divmod(total_minutes, 24 * 60)
    bj_weekday = ((weekday - 1 + day_delta) % 7) + 1
    return bj_weekday, bj_minutes // 60, bj_minutes % 60, day_delta


def _next_weekday(now: datetime, weekday: int, hour: int, minute: int) -> datetime:
    now = now.astimezone(BJ)
    days = (weekday - now.isoweekday()) % 7
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=days)
    if candidate <= now:
        candidate += timedelta(days=7)
    return candidate


def next_occurrence(
    now: datetime,
    weekday: int,
    hour: int,
    minute: int,
    timezone_name: str = "Asia/Shanghai",
) -> datetime:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    tz = ZoneInfo(timezone_name)
    local_now = now.astimezone(tz)
    days = (weekday - local_now.isoweekday()) % 7
    candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=days)
    if candidate <= local_now:
        candidate += timedelta(days=7)
    return candidate


def schedule_in_beijing(weekday: int, hour: int, minute: int) -> tuple[int, int, int]:
    bj_weekday, bj_hour, bj_minute, _ = jst_weekday_time_to_beijing(weekday, hour, minute)
    return bj_weekday, bj_hour, bj_minute


def schedule_time_in_timezone(schedule, timezone_name: str) -> tuple[int, int, int]:
    if timezone_name not in ("Asia/Shanghai", "Asia/Tokyo"):
        raise ValueError("display timezone must be Asia/Shanghai or Asia/Tokyo")
    offset_minutes = -60 if timezone_name == "Asia/Shanghai" else 0
    total_minutes = schedule.hour * 60 + schedule.minute + offset_minutes
    day_offset, clock_minutes = divmod(total_minutes, 24 * 60)
    weekday = ((schedule.weekday - 1 + day_offset) % 7) + 1
    return weekday, clock_minutes // 60, clock_minutes % 60


def next_schedule_occurrence(now: datetime, schedule) -> datetime:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now = now.astimezone(BJ)
    interval = max(1, int(getattr(schedule, "interval_days", 7) or 7))
    if schedule.start_date:
        try:
            start = date.fromisoformat(schedule.start_date[:10])
            day_offset, jst_minutes = divmod(schedule.hour * 60 + schedule.minute, 24 * 60)
            jst_start = datetime.combine(start + timedelta(days=day_offset), time(jst_minutes // 60, jst_minutes % 60), JST)
            first = jst_start.astimezone(BJ)
            if now <= first:
                return first
            elapsed = max(0, (now.date() - first.date()).days)
            rounds = elapsed // interval
            candidate = first + timedelta(days=rounds * interval)
            if candidate <= now:
                candidate += timedelta(days=interval)
            return candidate
        except ValueError:
            pass
    weekday, hour, minute = schedule_in_beijing(schedule.weekday, schedule.hour, schedule.minute)
    return next_occurrence(now, weekday, hour, minute)

