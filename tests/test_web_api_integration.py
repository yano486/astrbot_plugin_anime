from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from astrbot_plugin_anime.core.models import AnimeItem, Schedule, Subscription, Target
from astrbot_plugin_anime.core.store import JsonStore
from astrbot_plugin_anime.web.api import AnimeWebAPI


class WebApiIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_card_tests_cannot_use_another_targets_or_disabled_subscription(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(Path(directory) / "state.json")
            store.set_items([
                AnimeItem(key=key, title=key, item_type="tv", schedules=[Schedule(3, 22, 0, "22:00", "fixture")])
                for key in ("other", "mine", "disabled", "catalog-only")
            ])
            for target in ("group:A", "group:B", "group:empty"):
                store.upsert_target(Target(target, subscribed=True, whitelisted=True))
            store.set_subscription(Subscription("group:A", "mine"))
            store.set_subscription(Subscription("group:A", "disabled", enabled=False))
            store.set_subscription(Subscription("group:B", "other"))
            sent = []

            class Plugin:
                async def _deliver_card(self, target, item, mode):
                    sent.append((target, item.key, mode))

            plugin = Plugin()
            plugin.store = store
            api = AnimeWebAPI(plugin)
            for kind in ("reminder_card", "update_card"):
                for key in ("other", "disabled", "catalog-only", "missing"):
                    before = len(sent)
                    status, body = await api.execute("test-push", "POST", {}, {"target_id": "group:A", "kind": kind, "anime_key": key})
                    self.assertEqual(status, 400)
                    self.assertIn("订阅", body["error"])
                    self.assertEqual(len(sent), before)
                status, _ = await api.execute("test-push", "POST", {}, {"target_id": "group:A", "kind": kind, "anime_key": "mine"})
                self.assertEqual(status, 200)
                self.assertEqual(sent[-1][1], "mine")
            status, _ = await api.execute("test-push", "POST", {}, {"target_id": "group:A", "kind": "reminder_card"})
            self.assertEqual(status, 200)
            self.assertEqual(sent[-1][1], "mine")
            before = len(sent)
            status, body = await api.execute("test-push", "POST", {}, {"target_id": "group:empty", "kind": "reminder_card"})
            self.assertEqual(status, 400)
            self.assertEqual(len(sent), before)
            self.assertIn("未添加动画推送", body["error"])

    async def test_image_tests_distinguish_inactive_target_and_no_anime_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(Path(directory) / "state.json")
            store.upsert_target(Target("off", subscribed=False))
            store.upsert_target(Target("empty", subscribed=True))
            store.set_subscription(Subscription("off", "a"))
            plugin = type("Plugin", (), {"store": store})()
            for target, expected in (("off", "订阅群没有订阅"), ("empty", "未添加动画推送")):
                for kind in ("reminder_card", "update_card", "daily_table", "weekly_table"):
                    status, result = await AnimeWebAPI(plugin).execute("test-push", "POST", {}, {"target_id": target, "kind": kind})
                    self.assertEqual(status, 400)
                    self.assertIn(expected, result["error"])

    async def test_saving_empty_selection_keeps_subscription_enabled_and_uses_editable_notice(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(Path(directory) / "state.json")
            store.upsert_target(Target("group:A", subscribed=True, whitelisted=True))
            store.set_items([AnimeItem("a", "A", item_type="tv")])
            store.set_subscription(Subscription("group:A", "a"))
            store.set_preferences({"message_templates": {"push_no_anime": "未添加动画推送：自定义提示"}})
            plugin = type("Plugin", (), {"store": store})()
            api = AnimeWebAPI(plugin)
            status, _ = await api.execute("subscriptions", "POST", {}, {"target_id": "group:A", "subscriptions": []})
            self.assertEqual(status, 200)
            self.assertTrue(store.state["targets"]["group:A"]["subscribed"])
            self.assertEqual(store.get_subscriptions("group:A"), [])
            status, body = await api.execute("test-push", "POST", {}, {"target_id": "group:A", "kind": "weekly_table"})
            self.assertEqual(status, 400)
            self.assertEqual(body["error"], "未添加动画推送：自定义提示")

    async def test_disabled_target_image_tests_use_editable_subscription_notice(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(Path(directory) / "state.json")
            store.upsert_target(Target("disabled", enabled=False, subscribed=True))
            store.set_preferences({"message_templates": {"push_not_subscribed": "订阅群没有订阅：自定义提示"}})
            plugin = type("Plugin", (), {"store": store})()
            api = AnimeWebAPI(plugin)
            for kind in ("reminder_card", "update_card", "daily_table", "weekly_table"):
                status, body = await api.execute("test-push", "POST", {}, {"target_id": "disabled", "kind": kind})
                self.assertEqual(status, 400)
                self.assertEqual(body["error"], "订阅群没有订阅：自定义提示")
            status, _ = await api.execute("test-push", "POST", {}, {"target_id": "disabled", "kind": "message"})
            self.assertEqual(status, 400)
            status, _ = await api.execute("test-push", "POST", {}, {"target_id": "missing", "kind": "weekly_table"})
            self.assertEqual(status, 400)

    async def test_saved_card_layout_survives_reload_and_text_only_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            plugin = type("Plugin", (), {"store": JsonStore(state_path)})()
            api = AnimeWebAPI(plugin)
            status, _ = await api.execute("preferences", "POST", {}, {"card_style": "compact", "card_theme": "light"})
            self.assertEqual(status, 200)
            plugin.store = JsonStore(state_path)
            status, result = await api.execute("preferences", "POST", {}, {"message_templates": {"help_english": "updated"}})
            self.assertEqual(status, 200)
            self.assertEqual(result["preferences"]["card_style"], "compact")
            self.assertEqual(result["preferences"]["card_theme"], "light")

    async def test_saving_message_templates_preserves_other_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(Path(directory) / "state.json")
            store.set_preferences({
                "schedule_source": "yuc",
                "display_timezone": "Asia/Tokyo",
                "exclude_r18": True,
                "push_mode": "card",
            })

            class Plugin:
                def __init__(self):
                    self.store = store

            status, body = await AnimeWebAPI(Plugin()).execute(
                "preferences", "POST", {},
                {"message_templates": {"test_message": "custom message"}},
            )

            self.assertEqual(status, 200)
            self.assertEqual(body["preferences"]["schedule_source"], "yuc")
            self.assertEqual(body["preferences"]["display_timezone"], "Asia/Tokyo")
            self.assertTrue(body["preferences"]["exclude_r18"])
            self.assertEqual(body["preferences"]["push_mode"], "card")
            self.assertEqual(body["preferences"]["message_templates"]["test_message"], "custom message")

    async def test_preferences_return_template_definitions_and_save_push_mode(self):
        from astrbot_plugin_anime.core.store import JsonStore

        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(Path(directory) / "state.json")

            class Plugin:
                def __init__(self):
                    self.store = store

            plugin = Plugin()
            api = AnimeWebAPI(plugin)
            status, body = await api.execute("preferences", "GET", {})
            self.assertEqual(status, 200)
            self.assertTrue(any(item["key"] == "help_english" for item in body["template_definitions"]))

            status, body = await api.execute(
                "preferences", "POST", {},
                {"push_mode": "card", "message_templates": {"help_english": "custom help"}},
            )
            self.assertEqual(status, 200)
            self.assertEqual(body["preferences"]["push_mode"], "card")
            self.assertEqual(body["preferences"]["message_templates"]["help_english"], "custom help")

    async def test_astrbot_and_remote_servers_register_the_same_api_routes(self):
        from astrbot_plugin_anime.web.api import API_ROUTE_DEFINITIONS
        from astrbot_plugin_anime.web.server import create_remote_web_app

        class Context:
            def __init__(self):
                self.registered = []

            def register_web_api(self, path, handler, methods, description):
                self.registered.extend((path, method) for method in methods)

        class Plugin:
            def __init__(self):
                self.context = Context()
                self.remote_webui_enabled = True
                self.remote_webui_password_enabled = False
                self.remote_webui_url = ""

        plugin = Plugin()
        api = AnimeWebAPI(plugin)
        plugin.web_api = api
        api.register()
        expected = {
            (f"/astrbot_plugin_anime/{endpoint}", method)
            for endpoint, _, methods, _ in API_ROUTE_DEFINITIONS
            for method in methods
        }
        self.assertEqual(set(plugin.context.registered), expected)

        remote_app = create_remote_web_app(plugin, "")
        remote_routes = {
            (route.resource.canonical.removeprefix("/api"), route.method)
            for route in remote_app.router.routes()
            if route.resource.canonical.startswith("/api/")
            and route.resource.canonical not in ("/api/login", "/api/logout")
        }
        self.assertEqual(remote_routes, {
            (f"/{endpoint}", method)
            for endpoint, _, methods, _ in API_ROUTE_DEFINITIONS
            for method in methods
        })

    async def test_all_period_returns_cached_anime_across_seasons(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(Path(directory) / "state.json")
            store.set_items([
                AnimeItem("tv:summer", "Summer", season="2026-07", item_type="tv", region="jp"),
                AnimeItem("tv:fall", "Fall", season="2026-10", item_type="tv", region="jp"),
            ])
            store.set_movie_items([AnimeItem("movie:1", "Movie", item_type="movie", release_date="2026-12-01")])

            class Plugin:
                def __init__(self): self.store = store
                @staticmethod
                def current_season(): return "2026-10"

            status, body = await AnimeWebAPI(Plugin()).execute("items", "GET", {"season": "all"})

            self.assertEqual(status, 200, body)
            self.assertEqual({item["key"] for item in body["items"]}, {"tv:summer", "tv:fall", "movie:1"})

    async def test_year_refresh_fetches_all_four_seasons(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(Path(directory) / "state.json")

            class RefreshService:
                def __init__(self): self.seasons = []
                async def refresh(self, season):
                    self.seasons.append(season)
                    return {"items": [], "sources": {}}
                async def refresh_movies(self, today):
                    return {"items": [], "sources": {}}

            class Plugin:
                def __init__(self):
                    self.store = store
                    self.refresh_service = RefreshService()
                @staticmethod
                def current_season(): return "2026-10"

            plugin = Plugin()
            status, body = await AnimeWebAPI(plugin).execute("refresh", "POST", {}, {"season": "2026"})

            self.assertEqual(status, 200, body)
            self.assertEqual(plugin.refresh_service.seasons, ["2026-01", "2026-04", "2026-07", "2026-10"])
            self.assertEqual(body["count"], 0)

    async def test_selected_seasons_refresh_only_requested_quarters_and_movies_once(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(Path(directory) / "state.json")

            class RefreshService:
                def __init__(self): self.seasons = []; self.movie_calls = 0
                async def refresh(self, season):
                    self.seasons.append(season)
                    return {"items": [], "sources": {}}
                async def refresh_movies(self, today):
                    self.movie_calls += 1
                    return {"items": [], "sources": {}}

            class Plugin:
                def __init__(self):
                    self.store = store
                    self.refresh_service = RefreshService()
                @staticmethod
                def current_season(): return "2026-10"

            plugin = Plugin()
            status, body = await AnimeWebAPI(plugin).execute(
                "refresh", "POST", {}, {"seasons": ["2026-01", "2026-04"]}
            )

            self.assertEqual(status, 200, body)
            self.assertEqual(plugin.refresh_service.seasons, ["2026-01", "2026-04"])
            self.assertEqual(plugin.refresh_service.movie_calls, 1)

    async def test_refresh_preserves_requested_priority_order(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(Path(directory) / "state.json")

            class RefreshService:
                def __init__(self): self.seasons = []
                async def refresh(self, season):
                    self.seasons.append(season)
                    return {"items": [], "sources": {}}
                async def refresh_movies(self, today):
                    return {"items": [], "sources": {}}

            class Plugin:
                def __init__(self):
                    self.store = store
                    self.refresh_service = RefreshService()
                @staticmethod
                def current_season(): return "2026-07"

            plugin = Plugin()
            status, _ = await AnimeWebAPI(plugin).execute(
                "refresh", "POST", {}, {"seasons": ["2026-07", "2026-10", "2027-01", "2026-04"]}
            )
            self.assertEqual(status, 200)
            self.assertEqual(plugin.refresh_service.seasons, ["2026-07", "2026-10", "2027-01", "2026-04"])

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
                    self.table_tests = []

                @staticmethod
                def current_season(): return "2026-10"

                async def _deliver(self, target, message):
                    self.messages.append((target, message))
                    return True

                async def _deliver_card(self, target, item, mode):
                    self.cards.append((target, item.key, mode))
                    return True

                class TableScheduler:
                    def __init__(self, owner):
                        self.owner = owner

                    async def send_test(self, target_id, kind):
                        self.owner.table_tests.append((target_id, kind))
                        return True

            plugin = Plugin()
            plugin.table_scheduler = plugin.TableScheduler(plugin)
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

            status, _ = await api.execute("test-push", "POST", {}, {
                "target_id": "group:1", "kind": "update_card", "anime_key": "tv:1",
            })
            self.assertEqual(status, 400)
            self.assertEqual(plugin.cards, [])
            store.set_subscription(Subscription("group:1", "tv:1"))

            for kind, expected_mode in (("reminder_card", "reminder"), ("update_card", "update")):
                status, body = await api.execute("test-push", "POST", {}, {
                    "target_id": "group:1", "kind": kind, "anime_key": "tv:1",
                })
                self.assertEqual(status, 200)
                self.assertTrue(body["sent"])
                self.assertEqual(plugin.cards[-1], ("group:1", "tv:1", expected_mode))

            for kind, table_kind in (("daily_table", "daily"), ("weekly_table", "weekly")):
                status, body = await api.execute("test-push", "POST", {}, {
                    "target_id": "group:1", "kind": kind,
                })
                self.assertEqual(status, 200)
                self.assertEqual(body, {"sent": True, "kind": kind})
                self.assertEqual(plugin.table_tests[-1], ("group:1", table_kind))

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
