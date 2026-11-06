from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo

from PIL import Image

from astrbot_plugin_anime.core.models import AnimeItem, Schedule
from astrbot_plugin_anime.rendering.push_tables import (
    airings_between,
    cleanup_generated_tables,
    upcoming_movies,
    render_airings_image,
    render_notification_card,
    render_subscription_table_image,
)


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

    def test_upcoming_movie_filter_covers_rest_of_year_and_next_year_in_december(self) -> None:
        movie = AnimeItem(key="m", title="Film", title_cn="剧场版", item_type="movie", region="jp", release_date="2026-12-01")
        ova = AnimeItem(key="o", title="OVA", item_type="ova", region="jp", release_date="2027-01-01")
        old = AnimeItem(key="old", title="Old", item_type="movie", region="jp", release_date="2026-09-01")
        rows = upcoming_movies([movie, ova, old], date(2026, 11, 3))
        self.assertEqual({row.item.key for row in rows}, {"m"})
        rows = upcoming_movies([movie, ova, old], date(2026, 12, 1))
        self.assertEqual({row.item.key for row in rows}, {"m", "o"})

    def test_weekly_schedule_can_render_as_day_bands(self) -> None:
        from astrbot_plugin_anime.rendering.push_tables import render_weekly_image

        rows = airings_between([self.item], datetime(2026, 10, 5, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")), datetime(2026, 10, 12, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")))
        with tempfile.TemporaryDirectory() as directory:
            path = render_weekly_image("本周动画播放表", rows, Path(directory) / "week.png")
            with Image.open(path) as image:
                self.assertEqual(image.format, "PNG")
                self.assertGreater(image.width, image.height)

    def test_combined_table_is_a_single_png(self) -> None:
        rows = airings_between([self.item], datetime(2026, 10, 6, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")), datetime(2026, 10, 7, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")))
        with tempfile.TemporaryDirectory() as directory:
            path = render_airings_image("今日动画", rows, Path(directory) / "today.png")
            with Image.open(path) as image:
                self.assertEqual(image.format, "PNG")
                self.assertEqual(image.width, 1200)
                self.assertGreater(image.height, 200)

    def test_notification_card_renders_for_reminder_and_update_modes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            for mode in ("reminder", "update"):
                path = render_notification_card(self.item, mode, Path(directory) / f"{mode}.png", "Asia/Tokyo")
                with Image.open(path) as image:
                    self.assertEqual(image.format, "PNG")
                    self.assertGreater(image.width, 500)

    def test_subscription_table_uses_fixed_dark_image_style(self) -> None:
        rows = airings_between(
            [self.item],
            datetime(2026, 10, 5, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            datetime(2026, 10, 12, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = render_subscription_table_image("每日订阅番表", rows, Path(directory) / "table.png")
            with Image.open(path) as image:
                self.assertEqual(image.getpixel((0, 0)), (13, 13, 24))

    def test_generated_table_cleanup_removes_only_expired_plugin_pngs(self) -> None:
        import os

        now = datetime(2026, 11, 4).timestamp()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expired = root / ("a" * 32 + ".png")
            recent = root / ("b" * 32 + ".png")
            unrelated = root / "keep.png"
            for path in (expired, recent, unrelated):
                path.write_bytes(b"test")
            os.utime(expired, (now - 8 * 86400, now - 8 * 86400))
            os.utime(recent, (now - 60, now - 60))

            removed = cleanup_generated_tables(root, now=now)

            self.assertEqual(removed, 1)
            self.assertFalse(expired.exists())
            self.assertTrue(recent.exists())
            self.assertTrue(unrelated.exists())


if __name__ == "__main__":
    unittest.main()
