from __future__ import annotations

import asyncio
from datetime import datetime
import unittest
from zoneinfo import ZoneInfo

from astrbot_plugin_anime.models import AnimeItem, Subscription, Target
from astrbot_plugin_anime.scheduler import ReminderScheduler


class Store:
    def __init__(self):
        self.items = [AnimeItem("movie:1", "Movie", title_cn="电影", item_type="movie", region="jp", release_date="2026-11-04", data_status="time_unknown")]
        self.subs = [Subscription("group:1", "movie:1", lead_minutes=60, on_time=False)]
        self.state = {"targets": {"group:1": Target("group:1", whitelisted=True, subscribed=True).__dict__}, "receipts": []}
        self.release_override = ""

    def get_all_items(self): return self.items
    def get_items(self): return self.items
    def get_movie_release_override(self, key): return self.release_override if key == "movie:1" else ""
    def get_subscriptions(self): return self.subs
    def has_receipt(self, key): return key in self.state["receipts"]
    def add_receipt(self, key): self.state["receipts"].append(key)
    def save(self): pass


class MovieReminderTests(unittest.TestCase):
    def test_movie_release_date_can_trigger_lead_reminder(self):
        sent = []

        async def deliver(target, message):
            sent.append(message)
            return True

        now = datetime(2026, 11, 3, 23, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        count = asyncio.run(ReminderScheduler(Store(), deliver, interval=30).check_once(now))
        self.assertEqual(count, 1)
        self.assertIn("电影", sent[0])
        self.assertIn("来源只有日期", sent[0])

    def test_movie_can_use_webui_release_datetime_override(self):
        store = Store()
        store.release_override = "2026-11-04T08:00"
        sent = []

        async def deliver(target, message):
            sent.append(message)
            return True

        now = datetime(2026, 11, 4, 7, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        count = asyncio.run(ReminderScheduler(store, deliver, interval=30).check_once(now))
        self.assertEqual(count, 1)
        self.assertIn("08:00", sent[0])
        self.assertNotIn("来源只有日期", sent[0])
