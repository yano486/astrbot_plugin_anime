from __future__ import annotations

import asyncio
from datetime import datetime
import unittest
from zoneinfo import ZoneInfo

from astrbot_plugin_anime.models import AnimeItem, Schedule, Subscription, Target
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

    def test_conflicted_schedule_is_not_sent(self) -> None:
        item = AnimeItem(key="anime:1", title="Test", schedules=[Schedule(2, 22, 0, "22:00", "x")], data_status="conflict")
        store = FakeStore(item, Subscription("group:1", item.key, lead_minutes=0))
        sent = []

        async def deliver(target, message):
            sent.append(message)
            return True

        count = asyncio.run(ReminderScheduler(store, deliver).check_once(datetime(2026, 11, 3, 21, 0, tzinfo=ZoneInfo("Asia/Shanghai"))))
        self.assertEqual(count, 0)
        self.assertEqual(sent, [])

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
