from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo
from unittest.mock import patch

from PIL import Image, ImageDraw

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
                self.assertEqual(image.width, 1200)

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
                self.assertEqual(image.getpixel((0, 0)), (16, 27, 33))

    def test_all_image_types_support_layouts_without_drawing_sources(self) -> None:
        from astrbot_plugin_anime.rendering.push_tables import render_weekly_image

        self.item.sources = ["Bangumi", "YUC", "bgmlist"]
        self.item.schedule_note = "Bangumi / YUC conflict"
        self.item.cover_url = "https://example.com/cover.jpg"
        rows = airings_between([self.item], datetime(2026, 10, 5, tzinfo=ZoneInfo("Asia/Shanghai")), datetime(2026, 10, 12, tzinfo=ZoneInfo("Asia/Shanghai")))
        real_text = ImageDraw.ImageDraw.text
        with tempfile.TemporaryDirectory() as directory:
            cover = Path(directory) / "cover.png"
            Image.new("RGB", (160, 230), "#d94e22").save(cover)
            for style in ("info", "poster", "compact"):
                for theme in ("dark", "light"):
                    for renderer, args in (
                        (render_airings_image, ("今日动画", rows)),
                        (render_weekly_image, ("本周动画", rows)),
                        (render_subscription_table_image, ("每日订阅番表", rows)),
                        (render_notification_card, (self.item, "reminder")),
                        (render_notification_card, (self.item, "update")),
                    ):
                        text_drawn = []

                        def draw_text(draw, xy, text, *a, **kw):
                            text_drawn.append(str(text))
                            return real_text(draw, xy, text, *a, **kw)

                        with self.subTest(style=style, theme=theme, renderer=renderer.__name__), patch.object(ImageDraw.ImageDraw, "text", draw_text):
                            path = renderer(*args, Path(directory) / "render.png", card_style=style, card_theme=theme, covers={self.item.key: cover})
                            self.assertFalse(any(source.lower() in "\n".join(text_drawn).lower() for source in self.item.sources))
                            self.assertIn("测试动画", "\n".join(text_drawn))
                            with Image.open(path) as image:
                                self.assertEqual(image.width, 1200)
                                self.assertIn((217, 78, 34), [rgb for _, rgb in image.getcolors(image.width * image.height)])

    def test_invalid_layout_does_not_silently_render_another_style(self) -> None:
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(ValueError, "card_style"):
            render_notification_card(self.item, "reminder", Path(directory) / "invalid.png", card_style="bad")

    def test_empty_compact_weekdays_leave_space_for_date_and_count(self) -> None:
        from astrbot_plugin_anime.rendering.push_tables import render_weekly_image

        rows = airings_between([self.item], datetime(2026, 10, 5, tzinfo=ZoneInfo("Asia/Shanghai")), datetime(2026, 10, 12, tzinfo=ZoneInfo("Asia/Shanghai")))
        drawn = []
        real_text = ImageDraw.ImageDraw.text

        def draw_text(draw, xy, text, *args, **kwargs):
            drawn.append((xy, text))
            return real_text(draw, xy, text, *args, **kwargs)

        with tempfile.TemporaryDirectory() as directory, patch.object(ImageDraw.ImageDraw, "text", draw_text):
            render_weekly_image("本周番表", rows, Path(directory) / "empty-days.png", card_style="compact")
        weekday_y = [xy[1] for xy, text in drawn if xy[0] == 52 and text in ["周" + day for day in "一二三四五六日"]]
        self.assertEqual(len(weekday_y), 7)
        self.assertTrue(all(right - left >= 130 for left, right in zip(weekday_y, weekday_y[1:])))

    def test_display_times_mark_cross_midnight_and_movie_dates_stay_date_only(self):
        from astrbot_plugin_anime.rendering.push_tables import Airing

        drawn = []
        real_text = ImageDraw.ImageDraw.text

        def draw_text(draw, xy, text, *args, **kwargs):
            drawn.append(str(text))
            return real_text(draw, xy, text, *args, **kwargs)

        row = Airing(self.item, self.item.schedules[0], datetime(2026, 11, 11, 23, 30, tzinfo=ZoneInfo("Asia/Shanghai")))
        with tempfile.TemporaryDirectory() as directory, patch.object(ImageDraw.ImageDraw, "text", draw_text):
            render_airings_image("今日番表", [row], Path(directory) / "midnight.png")
            self.assertIn("日本 次日 00:30", drawn)
            drawn.clear()
            movie = AnimeItem(key="ova", title="OVA", item_type="ova", release_date="2027-01-15")
            render_notification_card(movie, "reminder", Path(directory) / "ova.png")
            self.assertIn("2027-01-15", drawn)
            self.assertFalse(any("00:00" in value for value in drawn))

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
