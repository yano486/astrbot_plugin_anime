from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from astrbot_plugin_anime.core.merge import merge_records
from astrbot_plugin_anime.core.models import AnimeItem, Schedule, SourceRecord
from astrbot_plugin_anime.core.store import JsonStore
from astrbot_plugin_anime.services.refresh import RefreshService
from astrbot_plugin_anime.sources.bangumi import BangumiAdapter
from astrbot_plugin_anime.sources.base import SourceResult


class MonthlyAdapter(BangumiAdapter):
    async def fetch_month(self, year, month, season=None):
        if month == 10:
            return SourceResult("bangumi", status="error", error="TimeoutError")
        if month == 11:
            return SourceResult(
                "bangumi",
                [
                    SourceRecord(
                        source="bangumi",
                        title="New show",
                        bangumi_id=2,
                        season=season,
                        cover_url="https://example.com/new.jpg",
                    )
                ],
            )
        return SourceResult("bangumi", status="empty")


class FixedAdapter:
    def __init__(self, result):
        self.result = result

    async def fetch(self, season):
        return self.result


class RefreshCoverTests(unittest.TestCase):
    def test_month_failure_is_reported_without_discarding_successful_months(self):
        result = asyncio.run(MonthlyAdapter().fetch("2026-10"))
        self.assertEqual(result.status, "error")
        self.assertIn("2026-10", result.error)
        self.assertIn("TimeoutError", result.error)
        self.assertEqual([record.bangumi_id for record in result.records], [2])

    def test_partial_month_refresh_keeps_old_cover_and_uses_new_month_data(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(Path(directory) / "state.json")
            store.set_items(
                [
                    AnimeItem(
                        key="bangumi:1",
                        title="Existing",
                        season="2026-10",
                        bangumi_id=1,
                        sources=["bangumi", "bgmlist"],
                        cover_url="https://example.com/old.jpg",
                        schedules=[Schedule(3, 0, 0, "00:00", "bgmlist")],
                    ),
                    AnimeItem(
                        key="bangumi:3",
                        title="Only in failed month",
                        season="2026-10",
                        bangumi_id=3,
                        sources=["bangumi"],
                        cover_url="https://example.com/retained.jpg",
                    ),
                ]
            )
            schedule = SourceRecord(
                source="bgmlist",
                title="Existing",
                bangumi_id=1,
                season="2026-10",
                schedules=[Schedule(3, 0, 0, "00:00", "bgmlist")],
            )
            result = asyncio.run(
                RefreshService(
                    None,
                    store,
                    [
                        MonthlyAdapter(),
                        FixedAdapter(SourceResult("bgmlist", [schedule])),
                    ],
                ).refresh("2026-10")
            )
            items = {item.key: item for item in store.get_items()}
            self.assertEqual(set(items), {"bangumi:1", "bangumi:2", "bangumi:3"})
            self.assertEqual(
                items["bangumi:1"].cover_url, "https://example.com/old.jpg"
            )
            self.assertEqual(items["bangumi:1"].schedules[0].hour, 0)
            self.assertEqual(
                items["bangumi:2"].cover_url, "https://example.com/new.jpg"
            )
            self.assertEqual(
                items["bangumi:3"].cover_url, "https://example.com/retained.jpg"
            )
            self.assertEqual(result["sources"]["bangumi"]["status"], "error")

    def test_blank_cover_never_erases_cached_url_but_new_url_can_replace_it(self):
        for fresh_url in ("", "https://example.com/revised.jpg"):
            with (
                self.subTest(fresh_url=fresh_url),
                tempfile.TemporaryDirectory() as directory,
            ):
                store = JsonStore(Path(directory) / "state.json")
                store.set_items(
                    [
                        AnimeItem(
                            key="bangumi:1",
                            title="Existing",
                            season="2026-10",
                            sources=["bangumi"],
                            cover_url="https://example.com/old.jpg",
                        )
                    ]
                )
                record = SourceRecord(
                    source="bgmlist",
                    title="Existing",
                    bangumi_id=1,
                    season="2026-10",
                    cover_url=fresh_url,
                )
                asyncio.run(
                    RefreshService(
                        None,
                        store,
                        [
                            FixedAdapter(SourceResult("bgmlist", [record])),
                        ],
                    ).refresh("2026-10")
                )
                self.assertEqual(
                    store.get_items()[0].cover_url,
                    fresh_url or "https://example.com/old.jpg",
                )

    def test_merge_uses_available_cover_independently_of_source_order(self):
        records = [
            SourceRecord(source="bgmlist", title="Existing", bangumi_id=1),
            SourceRecord(
                source="bangumi",
                title="Existing",
                bangumi_id=1,
                cover_url="https://example.com/cover.jpg",
            ),
        ]
        for ordered in (records, records[::-1]):
            self.assertEqual(
                merge_records(ordered)[0].cover_url, "https://example.com/cover.jpg"
            )


if __name__ == "__main__":
    unittest.main()
