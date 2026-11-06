from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timedelta
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

from ..core.diagnostics import get_plugin_logger
from ..core.time_utils import BJ
from ..rendering.push_tables import Airing, airings_between


logger = get_plugin_logger()
TableDelivery = Callable[[str, str, list[Airing], str], Awaitable[bool]]


class SubscriptionTableScheduler:
    def __init__(self, store: Any, deliver: TableDelivery, interval: float = 30.0):
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
                logger.exception("[anime] subscription table scheduler cycle failed")
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=self.interval)
            except asyncio.TimeoutError:
                continue

    async def check_once(self, now: datetime | None = None) -> int:
        preferences = self.store.get_preferences()
        display_timezone = str(preferences.get("display_timezone", "Asia/Shanghai"))
        zone = ZoneInfo(display_timezone)
        local_now = (now or datetime.now(BJ)).astimezone(zone)
        sent = 0
        if bool(preferences.get("daily_table_enabled")) and self._due(local_now, preferences.get("daily_table_time", "00:00")):
            sent += await self._send_for_all_targets("daily", local_now.date(), preferences)
        if (
            bool(preferences.get("weekly_table_enabled"))
            and local_now.isoweekday() == 1
            and self._due(local_now, preferences.get("weekly_table_time", "00:00"))
        ):
            monday = local_now.date() - timedelta(days=local_now.isoweekday() - 1)
            sent += await self._send_for_all_targets("weekly", monday, preferences)
        return sent

    async def send_test(self, target_id: str, kind: str, now: datetime | None = None) -> bool:
        if kind not in {"daily", "weekly"}:
            raise ValueError("kind must be daily or weekly")
        preferences = self.store.get_preferences()
        display_timezone = str(preferences.get("display_timezone", "Asia/Shanghai"))
        local_now = (now or datetime.now(BJ)).astimezone(ZoneInfo(display_timezone))
        start_date = local_now.date()
        if kind == "weekly":
            start_date -= timedelta(days=start_date.isoweekday() - 1)
        rows = self._rows_for_target(target_id, start_date, kind, display_timezone)
        return await self.deliver(target_id, kind, rows, display_timezone)

    async def _send_for_all_targets(self, kind: str, start_date: date, preferences: dict[str, Any]) -> int:
        display_timezone = str(preferences.get("display_timezone", "Asia/Shanghai"))
        sent = 0
        target_ids = {
            sub.target_id
            for sub in self.store.get_subscriptions()
            if sub.enabled
        }
        for target_id in sorted(target_ids):
            target = self.store.state.get("targets", {}).get(target_id, {})
            if not target.get("enabled", True) or not target.get("subscribed", False) or not target.get("whitelisted", False):
                continue
            receipt = f"subscription-table|{target_id}|{kind}|{start_date.isoformat()}"
            if self.store.has_receipt(receipt):
                continue
            rows = self._rows_for_target(target_id, start_date, kind, display_timezone)
            if not rows:
                continue
            try:
                success = await self.deliver(target_id, kind, rows, display_timezone)
            except Exception:
                logger.exception("[anime] subscription table delivery failed: target=%s kind=%s", target_id, kind)
                success = False
            if success:
                self.store.add_receipt(receipt)
                self.store.save()
                sent += 1
        return sent

    def _rows_for_target(self, target_id: str, start_date: date, kind: str, display_timezone: str) -> list[Airing]:
        zone = ZoneInfo(display_timezone)
        end_date = start_date + timedelta(days=1 if kind == "daily" else 7)
        start = datetime.combine(start_date, time.min, zone)
        end = datetime.combine(end_date, time.min, zone)
        keys = {
            sub.anime_key
            for sub in self.store.get_subscriptions()
            if sub.target_id == target_id and sub.enabled
        }
        get_all_items = getattr(self.store, "get_all_items", None) or self.store.get_items
        items = [
            item for item in get_all_items()
            if item.key in keys and item.item_type in ("tv", "web")
        ]
        return airings_between(items, start, end)

    def _due(self, now: datetime, value: Any) -> bool:
        try:
            hour, minute = str(value).split(":", 1)
            scheduled = now.replace(hour=int(hour), minute=int(minute), second=0, microsecond=0)
        except (AttributeError, TypeError, ValueError):
            return False
        grace = timedelta(seconds=max(120, self.interval * 2))
        return scheduled <= now < scheduled + grace
