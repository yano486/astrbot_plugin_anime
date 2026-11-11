from __future__ import annotations

from pathlib import Path
import json
import tempfile
import unittest

from astrbot_plugin_anime.core.models import Subscription, Target
from astrbot_plugin_anime.core.store import JsonStore
from astrbot_plugin_anime.rendering.templates import DEFAULT_MESSAGE_TEMPLATES


class StoreTests(unittest.TestCase):
    def test_previous_default_templates_use_current_terminology_after_upgrade(self):
        legacy = json.loads((Path(__file__).parent / "fixtures" / "legacy_message_templates.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text(json.dumps({"preferences": {"schedule_source": "yuc", "message_templates": legacy}}), encoding="utf-8")
            store = JsonStore(path)
            for key in legacy:
                self.assertEqual(store.get_preferences()["message_templates"][key], DEFAULT_MESSAGE_TEMPLATES[key])
            self.assertEqual(store.get_preferences()["schedule_source"], "yuc")
            store.save()
            self.assertEqual(JsonStore(path).get_preferences(), store.get_preferences())

    def test_upgrading_default_templates_does_not_change_custom_text(self):
        legacy = json.loads((Path(__file__).parent / "fixtures" / "legacy_message_templates.json").read_text(encoding="utf-8"))
        custom = {key: value + "\n自定义文本" for key, value in legacy.items()}
        custom["help_english"] = "Custom help text"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text(json.dumps({"preferences": {"message_templates": custom}}), encoding="utf-8")
            store = JsonStore(path)
            for key, value in custom.items():
                self.assertEqual(store.get_preferences()["message_templates"][key], value)

    def test_round_trip_and_target_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(Path(directory) / "state.json")
            store.upsert_target(Target("group:1", "Group 1"))
            store.upsert_target(Target("group:2", "Group 2"))
            store.set_preferences({"schedule_source": "bgmlist", "display_timezone": "Asia/Tokyo"})
            store.set_subscription(Subscription("group:1", "bangumi:1", lead_minutes=30))
            store.save()

            loaded = JsonStore(Path(directory) / "state.json")
            self.assertEqual([item.target_id for item in loaded.get_subscriptions("group:1")], ["group:1"])
            self.assertEqual(loaded.get_preferences()["schedule_source"], "bgmlist")
            self.assertEqual(loaded.get_preferences()["display_timezone"], "Asia/Tokyo")
            self.assertEqual(loaded.get_subscriptions("group:2"), [])

    def test_receipt_is_deduplicated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(Path(directory) / "state.json")
            store.add_receipt("one")
            store.add_receipt("one")
            self.assertTrue(store.has_receipt("one"))
            self.assertEqual(store.state["receipts"], ["one"])


if __name__ == "__main__":
    unittest.main()
