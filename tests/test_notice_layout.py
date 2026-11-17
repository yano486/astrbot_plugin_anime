from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from PIL import Image

from astrbot_plugin_anime.core.models import AnimeItem
from astrbot_plugin_anime.rendering.card_canvas import CardCanvas, font, lines
from astrbot_plugin_anime.rendering.card_layouts import render_notice


class NoticeLayoutTests(unittest.TestCase):
    def test_short_notice_is_narrower_and_shorter_than_long_notice(self):
        short = AnimeItem(
            key="short", title="Short title", title_cn="学生会也有洞！", item_type="tv"
        )
        long = replace(
            short,
            key="long",
            title="Original title " * 22,
            title_cn="被流放的魔术师在第二人生遇见新的伙伴" * 5,
        )
        at = datetime(2026, 11, 17, 23, tzinfo=ZoneInfo("Asia/Shanghai"))
        with tempfile.TemporaryDirectory() as directory:
            for style in ("info", "poster", "compact"):
                sizes = []
                for item in (short, long):
                    path = render_notice(
                        item,
                        "reminder",
                        Path(directory) / f"{item.key}.png",
                        occurrence=at,
                        card_style=style,
                    )
                    with Image.open(path) as image:
                        sizes.append(image.size)
                with self.subTest(style=style):
                    self.assertLess(sizes[0][0], sizes[1][0])
                    self.assertLess(sizes[0][1], sizes[1][1])
                    self.assertLessEqual(sizes[1][0], 1200)

    def test_wrapped_content_and_footer_never_overlap_or_leave_the_panel(self):
        item = AnimeItem(
            key="long",
            title="Original subtitle " * 36,
            title_cn="标题文字特别长的动画" * 9,
            item_type="tv",
            genres=["很长的分类标签" * 4, "漫画改"],
        )
        real_text = CardCanvas.text
        with tempfile.TemporaryDirectory() as directory:
            for style in ("info", "poster", "compact"):
                for theme in ("dark", "light"):
                    bounds = []

                    def draw_text(
                        canvas,
                        x,
                        y,
                        text,
                        size,
                        color="ink",
                        bold=False,
                        width=None,
                        bounds=bounds,
                    ):
                        end = real_text(canvas, x, y, text, size, color, bold, width)
                        bounds.append((text, y, end))
                        for line in lines(text, width, size, bold):
                            self.assertLessEqual(
                                x + font(size, bold).getlength(line), canvas.width - 48
                            )
                        self.assertLessEqual(end, canvas.image.height - 28)
                        return end

                    with (
                        self.subTest(style=style, theme=theme),
                        patch.object(CardCanvas, "text", draw_text),
                    ):
                        render_notice(
                            item,
                            "reminder",
                            Path(directory) / "card.png",
                            card_style=style,
                            card_theme=theme,
                        )
                    footer_top = bounds[-1][1]
                    self.assertLess(max(end for _, _, end in bounds[:-1]), footer_top)


if __name__ == "__main__":
    unittest.main()
