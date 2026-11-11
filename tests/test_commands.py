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


class CommandAliasTests(unittest.TestCase):
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
            self.assertEqual(generated[0][0:2], ("每日订阅番表", "Asia/Shanghai"))
            self.assertFalse(generated[0][2].exists())


if __name__ == "__main__":
    unittest.main()
