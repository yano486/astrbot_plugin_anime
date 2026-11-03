from __future__ import annotations

import asyncio
from datetime import date
import unittest

from astrbot_plugin_anime.sources.bangumi import BangumiAdapter
from astrbot_plugin_anime.sources.base import SourceResult
from astrbot_plugin_anime.models import SourceRecord


class FakeBangumiAdapter(BangumiAdapter):
    def __init__(self):
        super().__init__()
        self.months = []

    async def fetch_month(self, year, month, season=None):
        self.months.append((year, month))
        records = [SourceRecord(source="bangumi", title="Film", item_type="movie", release_date=f"{year}-{month:02d}-01")]
        return SourceResult("bangumi", records)


class BangumiMovieCatalogTests(unittest.TestCase):
    def test_catalog_fetches_current_year_and_next_year_only_in_december(self):
        adapter = FakeBangumiAdapter()
        result = asyncio.run(adapter.fetch_movies(date(2026, 11, 4)))
        self.assertEqual(adapter.months, [(2026, month) for month in range(1, 13)])
        self.assertEqual(len(result.records), 12)

        adapter = FakeBangumiAdapter()
        asyncio.run(adapter.fetch_movies(date(2026, 12, 1)))
        self.assertEqual(len(adapter.months), 24)
        self.assertEqual(adapter.months[-12:], [(2027, month) for month in range(1, 13)])

    def test_optional_api_token_is_sent_as_bearer_authorization(self):
        token = "unit" + "_test"
        self.assertEqual(BangumiAdapter(api_token=token)._headers()["Authorization"], "Bearer " + token)
        self.assertNotIn("Authorization", BangumiAdapter()._headers())


if __name__ == "__main__":
    unittest.main()
