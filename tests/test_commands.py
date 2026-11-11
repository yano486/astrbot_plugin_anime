from __future__ import annotations

import unittest
import asyncio
import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from support import install_astrbot_stubs

install_astrbot_stubs()

from astrbot_plugin_anime.main import AnimePlugin
from astrbot_plugin_anime.core.models import AnimeItem, Schedule, Subscription, Target
from astrbot_plugin_anime.core.store import JsonStore
from astrbot_plugin_anime.core.time_utils import BJ


class CommandAliasTests(unittest.TestCase):
    def test_daily_and_weekly_commands_render_only_current_conversation_subscriptions(self):
        class FixedNow(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 11, 11, 12, tzinfo=BJ).astimezone(tz or BJ)

        class Event:
            def __init__(self, target, action):
                self.unified_msg_origin = target
                self.message_str = "/anime " + action

            @staticmethod
            def plain_result(text):
                return text

        async def collect(plugin, event):
            return [value async for value in plugin.anime_command(event)]

        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(Path(directory) / "state.json")
            store.set_items([
                AnimeItem(key=key, title=key, item_type={"b": "web", "unknown": "unknown"}.get(key, "tv"), region="jp", schedules=[Schedule(3, 22, 0, "22:00", "fixture", start_date="2026-11-11")])
                for key in ("a", "b", "unknown", "disabled", "catalog-only")
            ])
            store.set_subscription(Subscription("bot:GroupMessage:A", "a"))
            store.set_subscription(Subscription("bot:GroupMessage:A", "disabled", enabled=False))
            store.set_subscription(Subscription("bot:GroupMessage:B", "b"))
            store.set_subscription(Subscription("bot:FriendMessage:42", "b"))
            store.set_subscription(Subscription("bot:GroupMessage:unknown", "unknown"))
            store.set_subscription(Subscription("bot:GroupMessage:empty", "disabled", enabled=False))
            for target in ("bot:GroupMessage:A", "bot:GroupMessage:B", "bot:FriendMessage:42", "bot:GroupMessage:empty", "bot:GroupMessage:unknown"):
                store.upsert_target(Target(target, subscribed=True, whitelisted=True))
            store.upsert_target(Target("bot:GroupMessage:off", subscribed=False))
            store.set_subscription(Subscription("bot:GroupMessage:off", "a"))
            plugin = AnimePlugin.__new__(AnimePlugin)
            plugin.store = store
            rendered = []

            async def render(event, title, rows):
                rendered.append([row.item.key for row in rows])
                return rendered[-1]

            plugin._send_airings_image = render
            with patch("astrbot_plugin_anime.main.datetime", FixedNow):
                for action in ("push", "推送", "week", "本周"):
                    for target, expected in (("bot:GroupMessage:A", ["a"]), ("bot:GroupMessage:B", ["b"]), ("bot:FriendMessage:42", ["b"]), ("bot:GroupMessage:unknown", ["unknown"])):
                        with self.subTest(action=action, target=target):
                            self.assertEqual(asyncio.run(collect(plugin, Event(target, action))), [expected])
                    for target, notice in (("bot:GroupMessage:none", "订阅群没有订阅"), ("bot:GroupMessage:off", "订阅群没有订阅"), ("bot:GroupMessage:empty", "未添加动画推送"), (None, "会话")):
                        before = len(rendered)
                        replies = asyncio.run(collect(plugin, Event(target, action)))
                        self.assertEqual(len(rendered), before)
                        self.assertIn(notice, replies[0])

    def test_english_and_chinese_help_use_independent_templates(self) -> None:
        class Store:
            @staticmethod
            def get_preferences():
                return {"message_templates": {"help_english": "EN HELP", "help_chinese": "CN HELP"}}

        class Event:
            message_str = "/anime help"

            @staticmethod
            def plain_result(text):
                return text

        async def collect(generator):
            return [value async for value in generator]

        plugin = AnimePlugin.__new__(AnimePlugin)
        plugin.store = Store()
        english = asyncio.run(collect(plugin.anime_command(Event(), "help")))
        chinese = asyncio.run(collect(plugin.help(Event())))
        self.assertEqual(english, ["EN HELP"])
        self.assertEqual(chinese, ["CN HELP"])

    def test_english_suffixes(self) -> None:
        for raw, expected in (("push", "push"), ("week", "week"), ("ova", "ova"), ("sub", "sub")):
            self.assertEqual(AnimePlugin._action_name(object(), raw)[0], expected)

    def test_chinese_suffixes(self) -> None:
        for raw, expected in (("推送", "push"), ("本周", "week"), ("剧场版", "ova"), ("订阅", "sub")):
            self.assertEqual(AnimePlugin._action_name(object(), raw)[0], expected)

    def test_suffix_can_be_parsed_from_full_chat_message(self) -> None:
        class Event:
            message_str = "/anime 推送"

        self.assertEqual(AnimePlugin._action_name(Event(), ""), ("push", ""))

    def test_airings_image_keeps_new_file_and_cleans_expired_generated_images(self) -> None:
        class Store:
            @staticmethod
            def get_preferences():
                return {"display_timezone": "Asia/Shanghai"}

        class Event:
            @staticmethod
            def image_result(path):
                return path

        async def run(directory):
            plugin = AnimePlugin.__new__(AnimePlugin)
            plugin.data_dir = Path(directory)
            plugin.store = Store()
            generated = []

            def render(title, rows, path, timezone, **options):
                self.assertEqual(options["card_style"], "info")
                Path(path).write_bytes(b"new")
                generated.append(Path(path))

            with patch("astrbot_plugin_anime.main.render_airings_image", side_effect=render):
                result = await plugin._send_airings_image(Event(), "今日动画", [])
            return Path(result), generated

        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / "push_tables"
            output_dir.mkdir()
            expired = output_dir / ("c" * 32 + ".png")
            expired.write_bytes(b"old")
            old_time = datetime.now().timestamp() - 8 * 86400
            os.utime(expired, (old_time, old_time))

            result, generated = asyncio.run(run(directory))

            self.assertFalse(expired.exists())
            self.assertEqual(result, generated[0])
            self.assertTrue(result.exists())

    def test_subscription_table_delivery_uses_fixed_renderer_and_cleans_file(self) -> None:
        class Store:
            @staticmethod
            def get_preferences():
                return {"display_timezone": "Asia/Shanghai", "card_style": "poster", "card_theme": "light"}

        class Context:
            def __init__(self):
                self.sent = []

            async def send_message(self, target, chain):
                self.sent.append((target, chain))
                return True

        async def run(directory):
            plugin = AnimePlugin.__new__(AnimePlugin)
            plugin.data_dir = Path(directory)
            plugin.store = Store()
            plugin.context = Context()
            generated = []

            def render(title, rows, path, timezone, **options):
                self.assertEqual(options["kind"], "daily")
                self.assertEqual(options["card_style"], "poster")
                self.assertEqual(options["card_theme"], "light")
                Path(path).parent.mkdir(parents=True, exist_ok=True)
                Path(path).write_bytes(b"table")
                generated.append((title, timezone, Path(path)))

            with patch("astrbot_plugin_anime.main.render_subscription_table_image", side_effect=render):
                result = await plugin._deliver_subscription_table("group:1", "daily", [], "Asia/Shanghai")
            return result, plugin.context.sent, generated

        with tempfile.TemporaryDirectory() as directory:
            result, sent, generated = asyncio.run(run(directory))

            self.assertTrue(result)
            self.assertEqual(sent[0][0], "group:1")
            self.assertEqual(generated[0][0:2], ("每日订阅番组", "Asia/Shanghai"))
            self.assertFalse(generated[0][2].exists())

    def test_weekly_command_title_still_uses_seven_day_renderer_after_rename(self):
        class Store:
            @staticmethod
            def get_preferences():
                return {"display_timezone": "Asia/Shanghai"}

        class Event:
            @staticmethod
            def image_result(path):
                return path

        async def run(directory):
            plugin = AnimePlugin.__new__(AnimePlugin)
            plugin.data_dir = Path(directory)
            plugin.store = Store()
            with patch("astrbot_plugin_anime.main.render_weekly_image") as weekly, patch("astrbot_plugin_anime.main.render_airings_image") as daily:
                await plugin._send_airings_image(Event(), "本周订阅番组", [])
                weekly.assert_called_once()
                daily.assert_not_called()

        with tempfile.TemporaryDirectory() as directory:
            asyncio.run(run(directory))


if __name__ == "__main__":
    unittest.main()
