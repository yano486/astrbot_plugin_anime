from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
