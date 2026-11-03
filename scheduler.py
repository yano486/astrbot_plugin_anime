from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
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
        items = {item.key: item for item in self.store.get_items()}
        sent = 0
        for sub in self.store.get_subscriptions():
            if not sub.enabled:
                continue
            item = items.get(sub.anime_key)
            if not item or item.data_status in ("conflict", "time_unknown"):
                continue
            target = self.store.state.get("targets", {}).get(sub.target_id, {})
            if not target.get("enabled", True) or not target.get("subscribed", False) or not target.get("whitelisted", False):
                continue
            for schedule in item.schedules:
                grace = timedelta(seconds=max(120, self.interval * 2))
                occurrence = next_schedule_occurrence(now - timedelta(minutes=sub.lead_minutes) - grace, schedule)
                lead_at = occurrence - timedelta(minutes=sub.lead_minutes)
                for kind, due_at in (("lead", lead_at), ("on_time", occurrence)):
                    if kind == "lead" and sub.lead_minutes <= 0:
                        continue
                    if kind == "on_time" and not sub.on_time:
                        continue
                    key = f"{sub.target_id}|{item.key}|{occurrence.isoformat()}|{kind}"
                    if self.store.has_receipt(key) or not (due_at <= now < due_at + grace):
                        continue
                    message = self._message(item, schedule, kind)
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
    def _message(item: AnimeItem, schedule: Any, kind: str) -> str:
        from .formatters import format_reminder

        return format_reminder(item, schedule, "即将播出" if kind == "lead" else "按时开播")

