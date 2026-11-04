from __future__ import annotations

import unittest

from astrbot_plugin_anime.models import Schedule
from astrbot_plugin_anime.schedule_utils import schedule_sort_key


class ScheduleUtilsTests(unittest.TestCase):
    def test_extended_clock_sort_key_moves_occurrence_to_the_next_weekday(self) -> None:
        schedule = Schedule(weekday=1, hour=25, minute=30, raw_time="25:30", source="fixture")

        self.assertEqual(schedule_sort_key(schedule), (1, 90))


if __name__ == "__main__":
    unittest.main()
