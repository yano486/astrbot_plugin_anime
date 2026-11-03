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


if __name__ == "__main__":
    unittest.main()
