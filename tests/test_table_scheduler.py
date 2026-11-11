from __future__ import annotations

import asyncio
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from astrbot_plugin_anime.core.models import AnimeItem, Schedule, Subscription, Target
from astrbot_plugin_anime.services.table_scheduler import SubscriptionTableScheduler


class TableStore:
    def __init__(self, items, subscriptions, preferences):
        self.items = items
        self.subscriptions = subscriptions
        self.preferences = preferences
        self.state = {
            "targets": {
                target_id: Target(target_id, whitelisted=True, subscribed=True).__dict__
                for target_id in {sub.target_id for sub in subscriptions}
            },
            "receipts": [],
        }

    def get_all_items(self):
        return self.items

    def get_subscriptions(self):
        return self.subscriptions

    def get_preferences(self):
        return self.preferences

    def has_receipt(self, key):
        return key in self.state["receipts"]

    def add_receipt(self, key):
        self.state["receipts"].append(key)

    def save(self):
        pass


class SubscriptionTableSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.monday = AnimeItem(
            key="tv:monday",
            title="Monday",
            title_cn="周一动画",
            item_type="tv",
            schedules=[Schedule(weekday=1, hour=20, minute=0, raw_time="20:00", source="fixture", start_date="2026-11-02")],
        )
        self.tuesday = AnimeItem(
            key="web:tuesday",
            title="Tuesday",
            title_cn="周二动画",
            item_type="web",
            schedules=[Schedule(weekday=2, hour=21, minute=0, raw_time="21:00", source="fixture", start_date="2026-11-03")],
        )
        self.preferences = {
            "display_timezone": "Asia/Shanghai",
            "daily_table_enabled": True,
            "daily_table_time": "00:00",
            "weekly_table_enabled": True,
            "weekly_table_time": "00:00",
        }

    def test_daily_push_uses_only_each_target_subscriptions_for_that_date(self):
        store = TableStore(
            [self.monday, self.tuesday],
            [Subscription("group:one", self.monday.key), Subscription("group:two", self.tuesday.key)],
            {**self.preferences, "weekly_table_enabled": False},
        )
        sent = []

        async def deliver(target_id, kind, rows, display_timezone):
            sent.append((target_id, kind, [row.item.key for row in rows], display_timezone))
            return True

        scheduler = SubscriptionTableScheduler(store, deliver, interval=30)
        count = asyncio.run(scheduler.check_once(datetime(2026, 11, 2, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))))

        self.assertEqual(count, 1)
        self.assertEqual(sent, [
            ("group:one", "daily", ["tv:monday"], "Asia/Shanghai"),
        ])

    def test_weekly_push_runs_only_on_monday_and_is_not_duplicated(self):
        store = TableStore(
            [self.monday, self.tuesday],
            [Subscription("group:one", self.monday.key), Subscription("group:one", self.tuesday.key)],
            {**self.preferences, "daily_table_enabled": False},
        )
        sent = []

        async def deliver(target_id, kind, rows, display_timezone):
            sent.append((target_id, kind, [row.item.key for row in rows]))
            return True

        scheduler = SubscriptionTableScheduler(store, deliver, interval=30)
        monday = datetime(2026, 11, 2, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        self.assertEqual(asyncio.run(scheduler.check_once(monday)), 1)
        self.assertEqual(asyncio.run(scheduler.check_once(monday.replace(second=30))), 0)
        self.assertEqual(asyncio.run(scheduler.check_once(datetime(2026, 11, 3, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")))), 0)
        self.assertEqual(sent, [("group:one", "weekly", ["tv:monday", "web:tuesday"])])

    def test_disabled_table_pushes_do_not_send(self):
        store = TableStore(
            [self.monday],
            [Subscription("group:one", self.monday.key)],
            {**self.preferences, "daily_table_enabled": False, "weekly_table_enabled": False},
        )
        sent = []

        async def deliver(*args):
            sent.append(args)
            return True

        scheduler = SubscriptionTableScheduler(store, deliver)
        count = asyncio.run(scheduler.check_once(datetime(2026, 11, 2, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))))

        self.assertEqual(count, 0)
        self.assertEqual(sent, [])

    def test_weekly_and_test_tables_never_include_other_targets_or_disabled_items(self):
        from dataclasses import replace

        disabled = replace(self.monday, key="disabled")
        catalog = replace(self.monday, key="catalog-only")
        store = TableStore(
            [self.monday, self.tuesday, disabled, catalog],
            [Subscription("group:A", self.monday.key), Subscription("group:A", disabled.key, enabled=False), Subscription("group:B", self.tuesday.key)],
            {**self.preferences, "daily_table_enabled": False},
        )
        sent = []

        async def deliver(target, kind, rows, timezone):
            sent.append((target, kind, [row.item.key for row in rows]))
            return True

        async def run():
            scheduler = SubscriptionTableScheduler(store, deliver)
            now = datetime(2026, 11, 2, tzinfo=ZoneInfo("Asia/Shanghai"))
            self.assertEqual(await scheduler.check_once(now), 2)
            self.assertEqual(sent[:2], [("group:A", "weekly", [self.monday.key]), ("group:B", "weekly", [self.tuesday.key])])
            for kind in ("daily", "weekly"):
                await scheduler.send_test("group:A", kind, now)
                self.assertEqual(sent[-1], ("group:A", kind, [self.monday.key]))
            await scheduler.send_test("group:empty", "weekly", now)
            self.assertEqual(sent[-1], ("group:empty", "weekly", []))

        asyncio.run(run())

    def test_tables_keep_subscribed_airings_without_type_labels_but_exclude_movies(self):
        from dataclasses import replace

        unknown = replace(self.monday, key="unknown", item_type="unknown")
        movies = [replace(self.monday, key=kind, item_type=kind) for kind in ("movie", "ova")]
        store = TableStore(
            [unknown, *movies, self.monday],
            [Subscription("group:A", item.key) for item in [unknown, *movies]],
            self.preferences,
        )
        sent = []

        async def deliver(target, kind, rows, timezone):
            sent.append((kind, [row.item.key for row in rows]))
            return True

        async def run():
            scheduler = SubscriptionTableScheduler(store, deliver)
            now = datetime(2026, 11, 2, tzinfo=ZoneInfo("Asia/Shanghai"))
            self.assertEqual(await scheduler.check_once(now), 2)
            for kind in ("daily", "weekly"):
                await scheduler.send_test("group:A", kind, now)
            self.assertEqual(sent, [(kind, [unknown.key]) for kind in ("daily", "weekly", "daily", "weekly")])

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
