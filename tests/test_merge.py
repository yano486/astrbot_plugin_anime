from __future__ import annotations

import unittest

from astrbot_plugin_anime.merge import merge_records
from astrbot_plugin_anime.models import Schedule, SourceRecord


def record(source: str, title: str, bangumi_id: int | None, hour: int) -> SourceRecord:
    return SourceRecord(
        source=source,
        title=title,
        title_cn="测试动画",
        bangumi_id=bangumi_id,
        region="jp",
        schedules=[Schedule(weekday=1, hour=hour, minute=0, raw_time=f"{hour}:00", source=source)],
    )


class MergeTests(unittest.TestCase):
    def test_same_bangumi_id_merges_and_retains_sources(self) -> None:
        items = merge_records([record("bangumi", "Test", 1, 20), record("yuc", "测试动画", 1, 20)])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].sources, ["bangumi", "yuc"])
        self.assertEqual(items[0].data_status, "ok")

    def test_unique_title_merges_without_id(self) -> None:
        items = merge_records([record("yuc", "Same Title", None, 20), record("youranimes", "Same Title", None, 20)])
        self.assertEqual(len(items), 1)

    def test_schedule_record_without_id_attaches_to_unique_bangumi_title(self) -> None:
        items = merge_records([record("bangumi", "Same Title", 44, 20), record("yuc", "Same Title", None, 20)])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].bangumi_id, 44)
        self.assertEqual(set(items[0].sources), {"bangumi", "yuc"})

    def test_conflicting_times_are_visible(self) -> None:
        items = merge_records([record("yuc", "Same Title", 2, 20), record("acgsecrets", "Same Title", 2, 21)])
        self.assertEqual(items[0].data_status, "conflict")
        self.assertEqual(len(items[0].schedules), 2)


if __name__ == "__main__":
    unittest.main()
