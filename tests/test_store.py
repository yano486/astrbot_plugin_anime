from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from astrbot_plugin_anime.core.models import Subscription, Target
from astrbot_plugin_anime.core.store import JsonStore


class StoreTests(unittest.TestCase):
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
