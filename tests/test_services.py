from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from astrbot_plugin_anime.models import AnimeItem, SourceRecord, Schedule
from astrbot_plugin_anime.services import RefreshService
from astrbot_plugin_anime.sources.base import SourceResult
from astrbot_plugin_anime.store import JsonStore


class FakeAdapter:
    def __init__(self, result):
        self.result = result

    async def fetch(self, season):
        return self.result


class RefreshTests(unittest.TestCase):
    def test_default_adapters_pause_acgsecrets_and_youranimes(self) -> None:
        service = RefreshService(None, JsonStore(Path("unused.json")))
        self.assertEqual({adapter.name for adapter in service.adapters}, {"bangumi", "bgmlist", "yuc"})

    def test_keeps_last_source_schedule_when_that_source_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(Path(directory) / "state.json")
            store.set_items([
                AnimeItem(
                    key="bangumi:1", title="Test", title_cn="測試", season="2026-10",
                    sources=["youranimes"],
                    schedules=[Schedule(weekday=2, hour=21, minute=25, raw_time="21:25", source="youranimes", start_date="2026-10-06")],
                    data_status="ok",
                )
            ])
            store.state["season"] = "2026-10"
            service = RefreshService(None, store, [FakeAdapter(SourceResult("youranimes", status="error", error="timeout"))])
            result = asyncio.run(service.refresh("2026-10"))
            self.assertEqual(len(result["items"]), 0)
            self.assertEqual(len(store.get_items()), 1)
            self.assertEqual(store.state["source_status"]["youranimes"]["status"], "error")

    def test_failed_source_schedule_is_retained_but_unified_to_earliest_time(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(Path(directory) / "state.json")
            store.set_items([AnimeItem(
                key="bangumi:2", title="Test", season="2026-10", sources=["yuc"],
                schedules=[Schedule(1, 1, 40, "01:40", "yuc")], data_status="ok",
            )])
            current = SourceRecord(
                source="bangumi", title="Test", bangumi_id=2, region="jp",
                schedules=[Schedule(1, 1, 30, "01:30", "bangumi")],
            )
            service = RefreshService(None, store, [
                FakeAdapter(SourceResult("bangumi", [current])),
                FakeAdapter(SourceResult("yuc", status="error", error="temporary")),
            ])
            asyncio.run(service.refresh("2026-10"))
            item = store.get_items()[0]
            self.assertEqual(len(item.schedules), 1)
            self.assertEqual((item.schedules[0].hour, item.schedules[0].minute), (1, 30))
            self.assertIn("01:40", item.schedule_note)

    def test_refresh_applies_saved_single_source_preference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(Path(directory) / "state.json")
            store.set_preferences({"schedule_source": "yuc", "display_timezone": "Asia/Shanghai"})
            records = [
                SourceRecord(source="yuc", title="Test", bangumi_id=77, region="jp",
                             schedules=[Schedule(1, 22, 0, "22:00", "yuc")]),
                SourceRecord(source="bgmlist", title="Test", bangumi_id=77, region="jp",
                             schedules=[Schedule(1, 21, 0, "21:00", "bgmlist")]),
            ]
            adapters = [FakeAdapter(SourceResult(source, [record])) for source, record in (("yuc", records[0]), ("bgmlist", records[1]))]
            asyncio.run(RefreshService(None, store, adapters).refresh("2026-10"))

            item = store.get_items()[0]
            self.assertEqual(item.schedules[0].source, "yuc")
            self.assertEqual((item.schedules[0].hour, item.schedules[0].minute), (22, 0))


if __name__ == "__main__":
    unittest.main()
