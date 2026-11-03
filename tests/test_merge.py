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

    def test_different_source_times_use_the_earliest_japan_time(self) -> None:
        records = [
            SourceRecord(
                source=source,
                title="Same Title",
                bangumi_id=2,
                region="jp",
                schedules=[Schedule(1, 1, minute, f"01:{minute}", source)],
            )
            for source, minute in (("bgmlist", 30), ("bangumi", 40), ("yuc", 45))
        ]
        item = merge_records(records)[0]
        self.assertEqual(item.data_status, "ok")
        self.assertEqual(len(item.schedules), 1)
        self.assertEqual((item.schedules[0].hour, item.schedules[0].minute), (1, 30))
        self.assertIn("01:40", item.schedule_note)

    def test_schedule_source_can_be_limited_to_yuc_or_bgmlist(self) -> None:
        records = [
            SourceRecord(source=source, title="Same Title", bangumi_id=9, region="jp",
                         schedules=[Schedule(1, 1, minute, f"01:{minute:02d}", source)])
            for source, minute in (("yuc", 30), ("bgmlist", 45))
        ]

        yuc_item = merge_records(records, schedule_source="yuc")[0]
        bgmlist_item = merge_records(records, schedule_source="bgmlist")[0]
        earliest_item = merge_records(records, schedule_source="earliest")[0]

        self.assertEqual((yuc_item.schedules[0].source, yuc_item.schedules[0].minute), ("yuc", 30))
        self.assertEqual((bgmlist_item.schedules[0].source, bgmlist_item.schedules[0].minute), ("bgmlist", 45))
        self.assertEqual((earliest_item.schedules[0].source, earliest_item.schedules[0].minute), ("yuc", 30))

    def test_bangumi_time_mode_does_not_fall_back_to_other_source_time(self) -> None:
        records = [
            SourceRecord(source="bangumi", title="Same Title", bangumi_id=10, region="jp"),
            record("yuc", "Same Title", 10, 20),
        ]
        item = merge_records(records, schedule_source="bangumi")[0]

        self.assertEqual(item.schedules, [])
        self.assertEqual(item.data_status, "time_unknown")
        self.assertIn("Bangumi", item.schedule_note)

    def test_extended_clock_and_next_day_clock_are_not_a_conflict(self):
        first = SourceRecord(source="yuc", title="Test", bangumi_id=3,
                             schedules=[Schedule(1, 25, 30, "25:30", "yuc")])
        second = SourceRecord(source="youranimes", title="Test", bangumi_id=3,
                              schedules=[Schedule(2, 1, 30, "01:30", "youranimes")])
        self.assertEqual(merge_records([first, second])[0].data_status, "ok")

    def test_season_numbers_are_not_discarded_for_idless_titles(self):
        first = SourceRecord(source="yuc", title="Test Season 1")
        second = SourceRecord(source="yuc", title="Test Season 2")
        self.assertEqual(len(merge_records([first, second])), 2)

    def test_chinese_season_number_and_punctuation_match_sources_without_ids(self):
        records = [
            SourceRecord(source="bgmlist", title="转生贵族、鉴定技能扭转人生 第3期", bangumi_id=123, region="jp"),
            SourceRecord(source="yuc", title="转生贵族，鉴定技能扭转人生 第三季", region="unknown"),
        ]
        merged = merge_records(records)
        self.assertEqual(len(merged), 1)
        self.assertEqual(set(merged[0].sources), {"bgmlist", "yuc"})


if __name__ == "__main__":
    unittest.main()
