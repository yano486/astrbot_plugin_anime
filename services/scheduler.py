from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timedelta
from typing import Any, Awaitable, Callable

from ..core.diagnostics import get_plugin_logger
from ..core.models import AnimeItem, Subscription
from ..core.schedule_utils import schedule_sort_key
from ..core.time_utils import BJ, next_schedule_occurrence


logger = get_plugin_logger()


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
            try:
                await self.check_once(datetime.now(BJ))
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("[anime] scheduler cycle failed")
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
            preferences = self.store.get_preferences() if hasattr(self.store, "get_preferences") else {}
            movie_date_only = False
            if item.item_type in ("movie", "ova"):
                override = self.store.get_movie_release_override(item.key) if hasattr(self.store, "get_movie_release_override") else ""
                release_value = (override or item.release_date)[:10]
                occurrence = _release_occurrence(
                    release_value,
                    preferences.get("display_timezone", "Asia/Shanghai"),
                )
                movie_date_only = bool(release_value and len(release_value) == 10)
                schedule_entries = [(None, occurrence)] if occurrence else []
            else:
                if item.data_status == "conflict" and schedules:
                    schedules = [min(schedules, key=schedule_sort_key)]
                schedule_entries = [(schedule, None) for schedule in schedules]
            for schedule, fixed_occurrence in schedule_entries:
                grace = timedelta(seconds=max(120, self.interval * 2))
                if item.item_type in ("movie", "ova") and movie_date_only and fixed_occurrence:
                    grace = timedelta(days=1)
                occurrence = fixed_occurrence or next_schedule_occurrence(now - timedelta(minutes=sub.lead_minutes) - grace, schedule)
                lead_at = occurrence - timedelta(minutes=sub.lead_minutes)
                reminders = (("on_time", occurrence),) if item.item_type in ("movie", "ova") else (("lead", lead_at), ("on_time", occurrence))
                for kind, due_at in reminders:
                    if kind == "lead" and sub.lead_minutes <= 0:
                        continue
                    if kind == "on_time" and item.item_type not in ("movie", "ova") and not sub.on_time:
                        continue
                    key = f"{sub.target_id}|{item.key}|{occurrence.isoformat()}|{kind}"
                    if self.store.has_receipt(key) or not (due_at <= now < due_at + grace):
                        continue
                    message = self._message(
                        item,
                        schedule,
                        kind,
                        occurrence,
                        movie_date_only,
                        preferences.get("display_timezone", "Asia/Shanghai"),
                    )
                    delivery_exception = False
                    try:
                        success = await self.deliver(sub.target_id, message)
                    except Exception:
                        delivery_exception = True
                        logger.exception(
                            "[anime] reminder delivery failed: target=%s anime=%s kind=%s",
                            sub.target_id,
                            item.key,
                            kind,
                        )
                        success = False
                    if not success and not delivery_exception:
                        logger.error(
                            "[anime] reminder delivery was not accepted: target=%s anime=%s kind=%s",
                            sub.target_id,
                            item.key,
                            kind,
                        )
                    if success:
                        self.store.add_receipt(key)
                        self.store.save()
                        sent += 1
        return sent

    @staticmethod
    def _message(
        item: AnimeItem,
        schedule: Any,
        kind: str,
        occurrence: datetime | None = None,
        date_only: bool = False,
        display_timezone: str = "Asia/Shanghai",
    ) -> str:
        from ..rendering.formatters import format_reminder

        if item.item_type in ("movie", "ova"):
            from ..rendering.formatters import format_movie_reminder

            return format_movie_reminder(
                item,
                occurrence,
                "即将上映" if kind == "lead" else "按时上映",
                date_only,
                display_timezone,
            )
        return format_reminder(item, schedule, "即将播出" if kind == "lead" else "按时开播", display_timezone)


def _release_occurrence(value: str, timezone_name: str = "Asia/Shanghai") -> datetime | None:
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
    if len(value) == 10:
        from zoneinfo import ZoneInfo

        return datetime.combine(parsed.date(), time.min, ZoneInfo(timezone_name))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=BJ)
    return parsed.astimezone(BJ)
