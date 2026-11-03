from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo

from PIL import Image

from astrbot_plugin_anime.models import AnimeItem, Schedule
from astrbot_plugin_anime.push_tables import airings_between, upcoming_movies, render_airings_image


class PushTableTests(unittest.TestCase):
    def setUp(self) -> None:
        self.item = AnimeItem(
            key="bangumi:1",
            title="Title",
            title_cn="测试动画",
            season="2026-10",
            item_type="tv",
            schedules=[Schedule(weekday=1, hour=25, minute=30, raw_time="25:30", source="fixture", start_date="2026-10-05")],
        )

    def test_airing_crossing_midnight_is_grouped_by_beijing_date(self) -> None:
        rows = airings_between([self.item], datetime(2026, 10, 5, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")), datetime(2026, 10, 6, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")))
        self.assertEqual(rows, [])
        rows = airings_between([self.item], datetime(2026, 10, 6, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")), datetime(2026, 10, 7, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].at.hour, 0)
        self.assertEqual(rows[0].at.minute, 30)

    def test_upcoming_movie_filter_uses_next_three_months(self) -> None:
        movie = AnimeItem(key="m", title="Film", title_cn="剧场版", item_type="movie", region="jp", release_date="2026-12-01")
        ova = AnimeItem(key="o", title="OVA", item_type="ova", region="jp", release_date="2027-01-01")
        old = AnimeItem(key="old", title="Old", item_type="movie", region="jp", release_date="2026-09-01")
        rows = upcoming_movies([movie, ova, old], date(2026, 11, 3), months=3)
        self.assertEqual({row.item.key for row in rows}, {"m", "o"})

    def test_combined_table_is_a_single_png(self) -> None:
        rows = airings_between([self.item], datetime(2026, 10, 6, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")), datetime(2026, 10, 7, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")))
        with tempfile.TemporaryDirectory() as directory:
            path = render_airings_image("今日动画", rows, Path(directory) / "today.png")
            with Image.open(path) as image:
                self.assertEqual(image.format, "PNG")
                self.assertEqual(image.width, 1200)
                self.assertGreater(image.height, 200)


if __name__ == "__main__":
    unittest.main()
