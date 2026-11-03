import json
from pathlib import Path
import tempfile
import unittest

from support import install_astrbot_stubs

install_astrbot_stubs()

from astrbot_plugin_anime.store import JsonStore


class RuntimeContractTests(unittest.IsolatedAsyncioTestCase):
    def test_config_schema_is_astrbot_field_mapping(self):
        path = Path(__file__).parents[1] / "_conf_schema.json"
        schema = json.loads(path.read_text(encoding="utf-8"))
        self.assertIsInstance(schema, dict)
        for field in schema.values():
            self.assertIsInstance(field, dict)
            self.assertIn("type", field)
        self.assertEqual(schema["remote_webui_host"]["default"], "0.0.0.0")
        self.assertEqual(schema["remote_webui_port"]["default"], 1876)
        self.assertIn("remote_webui_password", schema)
        self.assertIn("bangumi_api_token", schema)
        self.assertIn("bangumi_proxy", schema)
        self.assertNotIn("bangumi_proxy_host", schema)
        self.assertNotIn("bangumi_proxy_port", schema)
        self.assertIn("https://next.bgm.tv/demo/access-token", schema["bangumi_api_token"]["hint"])

    def test_plugin_diagnostics_use_a_rotating_file_with_automatic_retention(self):
        from astrbot_plugin_anime.diagnostics import configure_plugin_logging

        with tempfile.TemporaryDirectory() as directory:
            path = configure_plugin_logging(Path(directory), retention_days=7)
            self.assertEqual(path.name, "anime.log")
            logger = __import__("logging").getLogger("astrbot_plugin_anime")
            handlers = [handler for handler in logger.handlers if getattr(handler, "baseFilename", "") == str(path)]
            try:
                self.assertEqual(len(handlers), 1)
                self.assertEqual(handlers[0].backupCount, 7)
            finally:
                for handler in handlers:
                    logger.removeHandler(handler)
                    handler.close()

    async def test_sub_registers_and_whitelists_before_works_are_chosen(self):
        from astrbot_plugin_anime.main import AnimePlugin

        class Event:
            unified_msg_origin = "test:GroupMessage:123"
            platform_name = "test"
            message_str = "anime sub"

            def plain_result(self, text):
                return text

            def get_sender_name(self):
                return "test"

        with tempfile.TemporaryDirectory() as directory:
            plugin = object.__new__(AnimePlugin)
            plugin.store = JsonStore(Path(directory) / "state.json")
            replies = [value async for value in plugin.anime_command(Event(), "sub")]
            target = plugin.store.state["targets"][Event.unified_msg_origin]
            self.assertTrue(target["whitelisted"])
            self.assertTrue(target["subscribed"])
            self.assertTrue(replies)

    def test_sub_off_keeps_remaining_suffix_from_event(self):
        from astrbot_plugin_anime.main import AnimePlugin

        class Event:
            message_str = "anime sub off"

        self.assertEqual(AnimePlugin._action_name(Event(), "sub"), ("sub", "off"))

    def test_corrupt_store_is_not_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaises(ValueError):
                JsonStore(path)
            self.assertEqual(path.read_text(encoding="utf-8"), "{broken")

    def test_old_catalog_with_retired_sources_is_refreshed_after_upgrade(self):
        from astrbot_plugin_anime.main import AnimePlugin
        from astrbot_plugin_anime.models import AnimeItem

        with tempfile.TemporaryDirectory() as directory:
            plugin = object.__new__(AnimePlugin)
            plugin.store = JsonStore(Path(directory) / "state.json")
            plugin.store.state["season"] = plugin.current_season()
            plugin.store.state["source_status"] = {name: {} for name in ("bangumi", "bgmlist", "yuc")}
            plugin.store.set_items([AnimeItem("old", "Old", sources=["acgsecrets", "yuc"])])
            self.assertTrue(plugin._season_catalog_needs_refresh())
