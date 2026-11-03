from __future__ import annotations

from datetime import datetime
import unittest

from astrbot_plugin_anime.time_utils import (
    BJ,
    jst_weekday_time_to_beijing,
    next_occurrence,
    parse_broadcast_clock,
    next_schedule_occurrence,
)
from astrbot_plugin_anime.models import Schedule


class TimeUtilsTests(unittest.TestCase):
    def test_parse_25_30_as_extended_clock(self) -> None:
        self.assertEqual(parse_broadcast_clock("25:30~"), (25, 30))

    def test_jst_monday_25_30_becomes_beijing_tuesday_00_30(self) -> None:
        self.assertEqual(jst_weekday_time_to_beijing(1, 25, 30), (2, 0, 30, 1))

    def test_next_occurrence_rolls_to_next_week(self) -> None:
        now = datetime(2026, 11, 3, 20, 31, tzinfo=BJ)
        result = next_occurrence(now, 2, 20, 30)
        self.assertEqual(result, datetime(2026, 11, 10, 20, 30, tzinfo=BJ))

    def test_naive_now_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            next_occurrence(datetime(2026, 11, 3, 20, 0), 2, 20, 30)

    def test_first_occurrence_uses_source_date_and_extended_hour(self) -> None:
        schedule = Schedule(1, 25, 30, "25:30", "yuc", start_date="2026-10-05")
        now = datetime(2026, 10, 5, 23, 0, tzinfo=BJ)
        self.assertEqual(next_schedule_occurrence(now, schedule), datetime(2026, 10, 6, 0, 30, tzinfo=BJ))


if __name__ == "__main__":
    unittest.main()
