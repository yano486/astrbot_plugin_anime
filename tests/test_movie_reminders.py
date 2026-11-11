from __future__ import annotations

import asyncio
from datetime import datetime
import unittest
from zoneinfo import ZoneInfo

from astrbot_plugin_anime.core.models import AnimeItem, Subscription, Target
from astrbot_plugin_anime.services.scheduler import ReminderScheduler


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
    def test_movie_card_uses_date_override_without_tv_lead_time(self):
        store = Store()
        store.release_override = "2026-11-05"
        store.get_preferences = lambda: {"push_mode": "card", "display_timezone": "Asia/Shanghai"}
        cards = []

        async def text(*args):
            self.fail("card mode must not send a text message")

        async def card(target, item, mode, **options):
            cards.append((item.release_date, options["reminder_label"]))
            return True

        async def run():
            scheduler = ReminderScheduler(store, text, deliver_card=card)
            self.assertEqual(await scheduler.check_once(datetime(2026, 11, 4, tzinfo=ZoneInfo("Asia/Shanghai"))), 0)
            self.assertEqual(await scheduler.check_once(datetime(2026, 11, 5, tzinfo=ZoneInfo("Asia/Shanghai"))), 1)
            self.assertEqual(await scheduler.check_once(datetime(2026, 11, 5, tzinfo=ZoneInfo("Asia/Shanghai"))), 0)

        asyncio.run(run())
        self.assertEqual(cards, [("2026-11-05", "上映日期提醒")])

    def test_movie_release_date_does_not_use_tv_advance_minutes(self):
        sent = []

        async def deliver(target, message):
            sent.append(message)
            return True

        now = datetime(2026, 11, 3, 23, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        count = asyncio.run(ReminderScheduler(Store(), deliver, interval=30).check_once(now))
        self.assertEqual(count, 0)
        self.assertEqual(sent, [])

        count = asyncio.run(ReminderScheduler(Store(), deliver, interval=30).check_once(
            datetime(2026, 11, 4, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        ))
        self.assertEqual(count, 1)
        self.assertIn("电影", sent[0])
        self.assertIn("上映日期：北京时间 2026-11-04", sent[0])
        self.assertIn("仅按上映日期提醒", sent[0])

        sent.clear()
        count = asyncio.run(ReminderScheduler(Store(), deliver, interval=30).check_once(
            datetime(2026, 11, 4, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        ))
        self.assertEqual(count, 1)

        sent.clear()
        count = asyncio.run(ReminderScheduler(Store(), deliver, interval=30).check_once(
            datetime(2026, 11, 5, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        ))
        self.assertEqual(count, 0)

    def test_movie_can_use_webui_release_date_override(self):
        store = Store()
        store.release_override = "2026-11-04"
        sent = []

        async def deliver(target, message):
            sent.append(message)
            return True

        now = datetime(2026, 11, 4, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        count = asyncio.run(ReminderScheduler(store, deliver, interval=30).check_once(now))
        self.assertEqual(count, 1)
        self.assertIn("上映日期：北京时间 2026-11-04", sent[0])

    def test_legacy_datetime_override_is_reduced_to_its_release_date(self):
        store = Store()
        store.release_override = "2026-11-04T08:00"
        sent = []

        async def deliver(target, message):
            sent.append(message)
            return True

        now = datetime(2026, 11, 4, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        count = asyncio.run(ReminderScheduler(store, deliver).check_once(now))
        self.assertEqual(count, 1)
        self.assertIn("2026-11-04", sent[0])

    def test_movie_date_reminder_uses_the_selected_timezone_day(self):
        store = Store()
        store.get_preferences = lambda: {"schedule_source": "earliest", "display_timezone": "Asia/Tokyo"}
        sent = []

        async def deliver(target, message):
            sent.append(message)
            return True

        now = datetime(2026, 11, 3, 23, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        count = asyncio.run(ReminderScheduler(store, deliver).check_once(now))
        self.assertEqual(count, 1)
        self.assertIn("上映日期：日本时间 2026-11-04", sent[0])
