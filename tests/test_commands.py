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

            def render(title, rows, path, timezone):
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


if __name__ == "__main__":
    unittest.main()
