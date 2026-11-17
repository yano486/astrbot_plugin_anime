from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from support import install_astrbot_stubs

install_astrbot_stubs()

from astrbot_plugin_anime.core.store import JsonStore
from astrbot_plugin_anime.main import AnimePlugin
from astrbot_plugin_anime.rendering.templates import DEFAULT_MESSAGE_TEMPLATES


class Event:
    def __init__(self, text):
        self.message_str = text

    def plain_result(self, text):
        return text


async def collect(generator):
    return [value async for value in generator]


class CommandEntryTests(unittest.TestCase):
    def setUp(self):
        self.plugin = AnimePlugin.__new__(AnimePlugin)
        self.plugin.store = type("Store", (), {"get_preferences": lambda self: {}})()

    def test_parent_command_does_not_duplicate_a_registered_subcommand(self):
        for suffix in (
            "help",
            "帮助",
            "push",
            "推送",
            "week",
            "本周",
            "ova",
            "剧场版",
            "sub off",
            "订阅 关闭",
            "bind",
            "绑定",
            "unbind",
            "解绑",
            "list",
            "列表",
            "refresh",
            "刷新",
        ):
            with self.subTest(suffix=suffix):
                event = Event("anime " + suffix)
                self.assertEqual(
                    asyncio.run(collect(self.plugin.anime_command(event))), []
                )

    def test_bare_and_unknown_commands_still_return_usage(self):
        class Store:
            def get_preferences(self):
                return {"message_templates": {"command_usage": "usage"}}

        self.plugin.store = Store()
        for text in ("anime", "anime unknown"):
            self.assertEqual(
                asyncio.run(collect(self.plugin.anime_command(Event(text)))), ["usage"]
            )

    def test_exposed_push_entries_keep_existing_action_dispatch(self):
        async def existing_dispatch(event, action=""):
            yield "result:" + self.plugin._action_name(event, action)[0]

        self.plugin._run_anime_command = existing_dispatch
        for handler_name, action, forms in (
            ("push", "push", ("anime push", "anime 推送", "anime推送")),
            ("week", "week", ("anime week", "anime 本周", "anime本周")),
            ("ova", "ova", ("anime ova", "anime 剧场版", "anime剧场版")),
            ("subscribe", "sub", ("anime sub", "anime 订阅", "anime订阅")),
        ):
            for text in forms:
                with self.subTest(text=text):
                    handler = getattr(self.plugin, handler_name)
                    self.assertEqual(
                        asyncio.run(collect(handler(Event(text)))), ["result:" + action]
                    )

    def test_chinese_help_keeps_the_chinese_template(self):
        class Store:
            def get_preferences(self):
                return {
                    "message_templates": {
                        "help_chinese": "中文帮助",
                        "help_english": "English help",
                    }
                }

        self.plugin.store = Store()
        self.assertEqual(
            asyncio.run(collect(self.plugin.help(Event("anime帮助")))), ["中文帮助"]
        )
        self.assertEqual(
            asyncio.run(collect(self.plugin.english_help(Event("anime help")))),
            ["English help"],
        )

    def test_legacy_uppercase_english_action_still_works(self):
        async def existing_dispatch(event, action=""):
            yield self.plugin._action_name(event, action)[0]

        self.plugin._run_anime_command = existing_dispatch
        self.assertEqual(
            asyncio.run(collect(self.plugin.anime_command(Event("anime PUSH")))),
            ["push"],
        )

    def test_english_and_chinese_disable_commands_keep_the_off_argument(self):
        from astrbot_plugin_anime.core.models import Target

        for text in ("anime sub off", "anime订阅 关闭", "anime 订阅 关闭"):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as directory:
                self.plugin.store = JsonStore(Path(directory) / "state.json")
                self.plugin.store.upsert_target(
                    Target("test:FriendMessage:123", subscribed=True, whitelisted=True)
                )
                event = Event(text)
                event.unified_msg_origin = "test:FriendMessage:123"
                output = asyncio.run(collect(self.plugin.subscribe(event)))
                target = self.plugin.store.get_targets()[0]
                self.assertEqual(len(output), 1)
                self.assertFalse(target.subscribed)
                self.assertFalse(target.whitelisted)

    def test_previous_default_help_is_updated_but_custom_text_is_preserved(self):
        previous = json.loads(
            (
                Path(__file__).parent / "fixtures/message_templates_0_3_23.json"
            ).read_text(encoding="utf-8")
        )
        for custom in (False, True):
            with (
                self.subTest(custom=custom),
                tempfile.TemporaryDirectory() as directory,
            ):
                path = Path(directory) / "state.json"
                values = {
                    key: value + ("\n自定义内容" if custom else "")
                    for key, value in previous.items()
                }
                path.write_text(
                    json.dumps({"preferences": {"message_templates": values}}),
                    encoding="utf-8",
                )
                store = JsonStore(path)
                actual = store.get_preferences()["message_templates"]
                for key, value in values.items():
                    self.assertEqual(
                        actual[key],
                        value if custom else DEFAULT_MESSAGE_TEMPLATES[key],
                    )
                store.save()
                self.assertEqual(
                    JsonStore(path).get_preferences(), store.get_preferences()
                )


if __name__ == "__main__":
    unittest.main()
