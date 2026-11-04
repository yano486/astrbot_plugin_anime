from __future__ import annotations

import asyncio
from datetime import datetime
import io
import logging
import unittest
from zoneinfo import ZoneInfo

from astrbot_plugin_anime.models import AnimeItem, Schedule, Subscription, Target
from astrbot_plugin_anime import scheduler as scheduler_module
from astrbot_plugin_anime.scheduler import ReminderScheduler


class FakeStore:
    def __init__(self, item: AnimeItem, sub: Subscription):
        self.items = [item]
        self.subs = [sub]
        self.state = {"targets": {sub.target_id: Target(sub.target_id, whitelisted=True, subscribed=True).__dict__}, "receipts": []}

    def get_items(self):
        return self.items

    def get_subscriptions(self):
        return self.subs

    def has_receipt(self, key):
        return key in self.state["receipts"]

    def add_receipt(self, key):
        self.state["receipts"].append(key)

    def save(self):
        pass


class SchedulerTests(unittest.TestCase):
    def test_scheduler_loop_continues_after_a_cycle_raises(self) -> None:
        async def run():
            item = AnimeItem(key="anime:loop", title="Test")
            sub = Subscription("group:loop", item.key)
            scheduler = ReminderScheduler(FakeStore(item, sub), lambda *_: asyncio.sleep(0), interval=0.001)
            calls = 0

            async def check_once(now=None):
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise RuntimeError("temporary store failure")
                scheduler._stopped.set()
                return 0

            scheduler.check_once = check_once
            await scheduler._run()
            return calls

        logger = scheduler_module.logger
        handler = logging.StreamHandler(io.StringIO())
        previous_level = logger.level
        logger.setLevel(logging.ERROR)
        logger.addHandler(handler)
        try:
            calls = asyncio.run(run())
            logs = handler.stream.getvalue()
        finally:
            logger.removeHandler(handler)
            logger.setLevel(previous_level)
        self.assertEqual(calls, 2)
        self.assertIn("scheduler cycle failed", logs)

    def test_delivery_exception_is_logged_and_receipt_is_not_written(self) -> None:
        item = AnimeItem(
            key="anime:delivery",
            title="Test",
            schedules=[Schedule(weekday=2, hour=22, minute=0, raw_time="22:00", source="fixture")],
        )
        store = FakeStore(item, Subscription("group:delivery", item.key, lead_minutes=0))

        async def fail_delivery(target, message):
            raise RuntimeError("network unavailable")

        logger = scheduler_module.logger
        handler = logging.StreamHandler(io.StringIO())
        previous_level = logger.level
        logger.setLevel(logging.ERROR)
        logger.addHandler(handler)
        try:
            count = asyncio.run(ReminderScheduler(store, fail_delivery).check_once(
                datetime(2026, 11, 3, 21, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
            ))
            logs = handler.stream.getvalue()
        finally:
            logger.removeHandler(handler)
            logger.setLevel(previous_level)

        self.assertEqual(count, 0)
        self.assertEqual(store.state["receipts"], [])
        self.assertIn("reminder delivery failed", logs)

    def test_delivery_false_return_is_logged_and_receipt_is_not_written(self) -> None:
        item = AnimeItem(
            key="anime:not-sent",
            title="Test",
            schedules=[Schedule(weekday=2, hour=22, minute=0, raw_time="22:00", source="fixture")],
        )
        store = FakeStore(item, Subscription("group:not-sent", item.key, lead_minutes=0))

        async def reject_delivery(target, message):
            return False

        logger = scheduler_module.logger
        handler = logging.StreamHandler(io.StringIO())
        previous_level = logger.level
        logger.setLevel(logging.ERROR)
        logger.addHandler(handler)
        try:
            count = asyncio.run(ReminderScheduler(store, reject_delivery).check_once(
                datetime(2026, 11, 3, 21, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
            ))
            logs = handler.stream.getvalue()
        finally:
            logger.removeHandler(handler)
            logger.setLevel(previous_level)

        self.assertEqual(count, 0)
        self.assertEqual(store.state["receipts"], [])
        self.assertIn("reminder delivery was not accepted", logs)

    def test_due_lead_reminder_sends_once_and_records_receipt(self) -> None:
        schedule = Schedule(weekday=2, hour=22, minute=0, raw_time="22:00", source="fixture")
        item = AnimeItem(key="bangumi:1", title="Test", title_cn="测试", schedules=[schedule], sources=["fixture"], data_status="ok")
        sub = Subscription("group:1", item.key, lead_minutes=10, on_time=False)
        store = FakeStore(item, sub)
        sent = []

        async def deliver(target, message):
            sent.append((target, message))
            return True

        scheduler = ReminderScheduler(store, deliver, interval=30)
        now = datetime(2026, 11, 3, 20, 50, 10, tzinfo=ZoneInfo("Asia/Shanghai"))
        count = asyncio.run(scheduler.check_once(now))
        self.assertEqual(count, 1)
        self.assertEqual(len(sent), 1)
        self.assertIn("按排期提醒", sent[0][1])

    def test_display_timezone_changes_labels_not_the_trigger_instant(self) -> None:
        schedule = Schedule(weekday=3, hour=23, minute=0, raw_time="23:00", source="fixture")
        item = AnimeItem(key="anime:tz", title="Test", schedules=[schedule], data_status="ok")
        sub = Subscription("group:tz", item.key, lead_minutes=15, on_time=False)
        store = FakeStore(item, sub)
        store.get_preferences = lambda: {"display_timezone": "Asia/Tokyo", "schedule_source": "earliest"}
        sent = []

        async def deliver(target, message):
            sent.append(message)
            return True

        now = datetime(2026, 11, 4, 21, 45, tzinfo=ZoneInfo("Asia/Shanghai"))
        count = asyncio.run(ReminderScheduler(store, deliver).check_once(now))
        self.assertEqual(count, 1)
        self.assertIn("日本时间：周三 23:00", sent[0])
        self.assertIn("北京时间：周三 22:00", sent[0])

    def test_legacy_conflicted_schedule_is_not_silently_paused(self) -> None:
        item = AnimeItem(key="anime:1", title="Test", schedules=[Schedule(2, 22, 0, "22:00", "x")], data_status="conflict")
        store = FakeStore(item, Subscription("group:1", item.key, lead_minutes=0))
        sent = []

        async def deliver(target, message):
            sent.append(message)
            return True

        count = asyncio.run(ReminderScheduler(store, deliver).check_once(datetime(2026, 11, 3, 21, 0, tzinfo=ZoneInfo("Asia/Shanghai"))))
        self.assertEqual(count, 1)
        self.assertEqual(len(sent), 1)

    def test_target_must_be_whitelisted_and_subscribed(self) -> None:
        item = AnimeItem(key="anime:1", title="Test", schedules=[Schedule(2, 22, 0, "22:00", "x")], data_status="ok")
        store = FakeStore(item, Subscription("group:1", item.key, lead_minutes=0))
        store.state["targets"]["group:1"]["whitelisted"] = False
        sent = []

        async def deliver(target, message):
            sent.append(message)
            return True

        count = asyncio.run(ReminderScheduler(store, deliver).check_once(datetime(2026, 11, 3, 22, 0, tzinfo=ZoneInfo("Asia/Shanghai"))))
        self.assertEqual(count, 0)
        self.assertEqual(sent, [])


if __name__ == "__main__":
    unittest.main()
