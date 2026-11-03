from __future__ import annotations

from datetime import date
import unittest

from astrbot_plugin_anime.models import AnimeItem, Subscription
from astrbot_plugin_anime.push_tables import upcoming_movies
from astrbot_plugin_anime.store import JsonStore
from astrbot_plugin_anime.web_api import validate_subscriptions


class MovieCatalogTests(unittest.TestCase):
    def test_movie_window_contains_remaining_current_year_and_all_next_year(self) -> None:
        items = [
            AnimeItem("old", "Old", item_type="movie", region="jp", release_date="2026-01-01"),
            AnimeItem("dec", "December", item_type="movie", region="jp", release_date="2026-12-20"),
            AnimeItem("next", "Next", item_type="ova", region="jp", release_date="2027-12-31"),
            AnimeItem("later", "Later", item_type="movie", region="jp", release_date="2028-01-01"),
        ]
        rows = upcoming_movies(items, date(2026, 12, 1))
        self.assertEqual({row.item.key for row in rows}, {"dec", "next"})

    def test_movie_items_are_persisted_separately_but_subscribable(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(Path(directory) / "state.json")
            movie = AnimeItem("movie:1", "Movie", item_type="movie", region="jp", release_date="2027-01-01")
            store.set_movie_items([movie])
            store.upsert_target(__import__("astrbot_plugin_anime.models", fromlist=["Target"]).Target("group:1"))
            store.set_subscription(Subscription("group:1", movie.key, lead_minutes=60))
            store.save()
            loaded = JsonStore(Path(directory) / "state.json")
            self.assertEqual(loaded.get_movie_items()[0].key, movie.key)
            self.assertEqual(loaded.get_all_items()[0].item_type, "movie")
            values = validate_subscriptions({"target_id": "group:1", "subscriptions": [{"anime_key": movie.key}]}, {"group:1"}, {item.key for item in loaded.get_all_items()})
            self.assertEqual(values[0].anime_key, movie.key)
