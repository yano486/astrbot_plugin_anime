from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from astrbot_plugin_anime.models import AnimeItem, Schedule, Target
from astrbot_plugin_anime.store import JsonStore
from astrbot_plugin_anime.web_api import AnimeWebAPI


class WebApiIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_movie_catalog_selection_release_time_and_test_push_share_target_state(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(Path(directory) / "state.json")
            tv = AnimeItem(
                "tv:1", "TV", season="2026-10", item_type="tv", region="jp",
                schedules=[Schedule(3, 23, 0, "23:00", "yuc")],
            )
            movie = AnimeItem("movie:1", "Movie", item_type="movie", region="jp", release_date="2027-04-10")
            store.set_items([tv])
            store.set_movie_items([movie])
            store.upsert_target(Target("group:1", enabled=True))
            store.save()

            class Plugin:
                remote_webui_url = "监听 0.0.0.0:1876"
                remote_webui_enabled = True

                def __init__(self):
                    self.store = store
                    self.messages = []
                    self.cards = []

                @staticmethod
                def current_season(): return "2026-10"

                async def _deliver(self, target, message):
                    self.messages.append((target, message))
                    return True

                async def _deliver_card(self, target, item, mode):
                    self.cards.append((target, item.key, mode))
                    return True

            plugin = Plugin()
            api = AnimeWebAPI(plugin)
            status, body = await api.execute("items", "GET", {"season": "2026-10"})
            self.assertEqual(status, 200)
            self.assertEqual({item["key"] for item in body["items"]}, {"tv:1", "movie:1"})

            status, body = await api.execute("subscriptions", "POST", {}, {
                "target_id": "group:1", "subscriptions": [{"anime_key": "movie:1", "enabled": True}],
            })
            self.assertEqual(body["saved"], 1)
            target = store.state["targets"]["group:1"]
            self.assertTrue(target["whitelisted"])
            self.assertTrue(target["subscribed"])
            self.assertEqual(store.get_subscriptions("group:1")[0].lead_minutes, 0)

            status, body = await api.execute("movie-release", "POST", {}, {
                "anime_key": "movie:1", "release_at": "2027-04-10",
            })
            self.assertEqual(body["release_at"], "2027-04-10")
            self.assertEqual(store.get_movie_release_override("movie:1"), "2027-04-10")

            status, body = await api.execute("movie-release", "POST", {}, {
                "anime_key": "movie:1", "release_at": "",
            })
            self.assertEqual(body["release_at"], "")
            self.assertEqual(store.get_movie_release_override("movie:1"), "")

            status, body = await api.execute("test-push", "POST", {}, {"target_id": "group:1"})
            self.assertTrue(body["sent"])
            self.assertEqual(plugin.messages[0][0], "group:1")

            for kind, expected_mode in (("reminder_card", "reminder"), ("update_card", "update")):
                status, body = await api.execute("test-push", "POST", {}, {
                    "target_id": "group:1", "kind": kind, "anime_key": "tv:1",
                })
                self.assertEqual(status, 200)
                self.assertTrue(body["sent"])
                self.assertEqual(plugin.cards[-1], ("group:1", "tv:1", expected_mode))

            status, body = await api.execute("preferences", "POST", {}, {
                "schedule_source": "yuc", "display_timezone": "Asia/Tokyo",
            })
            self.assertEqual(status, 200)
            self.assertEqual(body["preferences"]["display_timezone"], "Asia/Tokyo")

            status, body = await api.execute("targets/umo", "POST", {}, {
                "umo": "default:FriendMessage:123456789",
            })
            self.assertEqual(status, 200)
            self.assertTrue(store.state["targets"][body["target_id"]]["whitelisted"])


if __name__ == "__main__":
    unittest.main()
