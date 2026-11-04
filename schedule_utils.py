from __future__ import annotations

from .models import Schedule


def schedule_sort_key(schedule: Schedule) -> tuple[int, int]:
    day_offset, clock_minutes = divmod(schedule.hour * 60 + schedule.minute, 24 * 60)
    weekday = (schedule.weekday - 1 + day_offset) % 7
    return weekday, clock_minutes
