from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timedelta
from typing import Any, Awaitable, Callable

from .models import AnimeItem, Subscription
from .time_utils import BJ, next_schedule_occurrence


class ReminderScheduler:
    def __init__(self, store: Any, deliver: Callable[[str, str], Awaitable[bool]], interval: float = 30.0):
        self.store = store
        self.deliver = deliver
        self.interval = interval
        self._task: asyncio.Task | None = None
        self._stopped = asyncio.Event()

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._stopped.clear()
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stopped.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        while not self._stopped.is_set():
            await self.check_once(datetime.now(BJ))
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=self.interval)
            except asyncio.TimeoutError:
                continue

    async def check_once(self, now: datetime | None = None) -> int:
        now = (now or datetime.now(BJ)).astimezone(BJ)
        get_all_items = getattr(self.store, "get_all_items", self.store.get_items)
        items = {item.key: item for item in get_all_items()}
        sent = 0
        for sub in self.store.get_subscriptions():
            if not sub.enabled:
                continue
            item = items.get(sub.anime_key)
            if not item or (item.data_status == "time_unknown" and item.item_type not in ("movie", "ova")):
                continue
            target = self.store.state.get("targets", {}).get(sub.target_id, {})
            if not target.get("enabled", True) or not target.get("subscribed", False) or not target.get("whitelisted", False):
                continue
            schedules = item.schedules
            movie_date_only = False
            if item.item_type in ("movie", "ova"):
                override = self.store.get_movie_release_override(item.key) if hasattr(self.store, "get_movie_release_override") else ""
                occurrence = _release_occurrence(override or item.release_date)
                movie_date_only = bool(not override and item.release_date and len(item.release_date) == 10)
                schedule_entries = [(None, occurrence)] if occurrence else []
            else:
                if item.data_status == "conflict" and schedules:
                    schedules = [min(schedules, key=_schedule_sort_key)]
                schedule_entries = [(schedule, None) for schedule in schedules]
            for schedule, fixed_occurrence in schedule_entries:
                grace = timedelta(seconds=max(120, self.interval * 2))
                occurrence = fixed_occurrence or next_schedule_occurrence(now - timedelta(minutes=sub.lead_minutes) - grace, schedule)
                lead_at = occurrence - timedelta(minutes=sub.lead_minutes)
                for kind, due_at in (("lead", lead_at), ("on_time", occurrence)):
                    if kind == "lead" and sub.lead_minutes <= 0:
                        continue
                    if kind == "on_time" and not sub.on_time:
                        continue
                    key = f"{sub.target_id}|{item.key}|{occurrence.isoformat()}|{kind}"
                    if self.store.has_receipt(key) or not (due_at <= now < due_at + grace):
                        continue
                    message = self._message(item, schedule, kind, occurrence, movie_date_only)
                    try:
                        success = await self.deliver(sub.target_id, message)
                    except Exception:
                        success = False
                    if success:
                        self.store.add_receipt(key)
                        self.store.save()
                        sent += 1
        return sent

    @staticmethod
    def _message(item: AnimeItem, schedule: Any, kind: str, occurrence: datetime | None = None, date_only: bool = False) -> str:
        from .formatters import format_reminder

        if item.item_type in ("movie", "ova"):
            from .formatters import format_movie_reminder

            return format_movie_reminder(item, occurrence, "即将上映" if kind == "lead" else "按时上映", date_only)
        return format_reminder(item, schedule, "即将播出" if kind == "lead" else "按时开播")


def _release_occurrence(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        try:
            parsed_date = date.fromisoformat(value[:10])
        except ValueError:
            return None
        parsed = datetime.combine(parsed_date, time.min)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=BJ)
    return parsed.astimezone(BJ)


def _schedule_sort_key(schedule: Any) -> tuple[int, int]:
    day_offset, clock_minutes = divmod(schedule.hour * 60 + schedule.minute, 24 * 60)
    weekday = (schedule.weekday - 1 + day_offset) % 7
    return weekday, clock_minutes

