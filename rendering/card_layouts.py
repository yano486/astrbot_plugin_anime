from __future__ import annotations

from math import ceil
from zoneinfo import ZoneInfo

from ..core.time_utils import BJ, JST, schedule_time_in_timezone
from .card_canvas import CardCanvas, font, text_height
from .swimlane import render_swimlane


CARD_STYLES = {"info", "poster", "compact"}
WEEKDAYS = "一二三四五六日"


def validate_style(style: str):
    if style not in CARD_STYLES:
        raise ValueError("card_style must be info, poster, or compact")


def item_title(item):
    return item.title_cn or item.title


def item_tags(item):
    types = {"tv": "TV", "web": "WEB", "ova": "OVA", "movie": "剧场版", "unknown": "动画"}
    return " · ".join([types.get(item.item_type, "动画"), *item.genres[:3]])


def render_table(title, rows, output, timezone="Asia/Shanghai", *, card_style="info", card_theme="dark", covers=None, weekly=False):
    validate_style(card_style)
    return render_swimlane(title, rows, output, timezone, theme=card_theme, covers=covers, weekly=weekly)


def render_notice(item, mode, output, timezone="Asia/Shanghai", *, card_style="info", card_theme="dark", covers=None, occurrence=None, reminder_label=None):
    validate_style(card_style)
    if mode not in {"reminder", "update"}:
        raise ValueError("mode must be reminder or update")
    covers = covers or {}
    label = reminder_label or ("动画开播提醒" if mode == "reminder" else "动画更新卡片")
    zone = ZoneInfo(timezone)
    zone_label = "北京时间" if timezone == "Asia/Shanghai" else "日本时间"
    if item.item_type in {"movie", "ova"}:
        primary, secondary = "上映日期", item.release_date[:10] or "日期待定"
    elif occurrence:
        local = occurrence.astimezone(zone)
        other = occurrence.astimezone(JST if timezone == "Asia/Shanghai" else BJ)
        primary = f"{zone_label}  {local:%m.%d} 周{WEEKDAYS[local.isoweekday() - 1]} {local:%H:%M}"
        secondary = ("日本时间" if timezone == "Asia/Shanghai" else "北京时间") + f"  {other:%m.%d %H:%M}"
    elif item.schedules:
        schedule = item.schedules[0]
        day, hour, minute = schedule_time_in_timezone(schedule, timezone)
        other_day, other_hour, other_minute = schedule_time_in_timezone(schedule, "Asia/Tokyo" if timezone == "Asia/Shanghai" else "Asia/Shanghai")
        primary = f"{zone_label}  周{WEEKDAYS[day - 1]} {hour:02}:{minute:02}"
        secondary = ("日本时间" if timezone == "Asia/Shanghai" else "北京时间") + f"  周{WEEKDAYS[other_day - 1]} {other_hour:02}:{other_minute:02}"
    else:
        primary, secondary = "时间待定", ""
    cover_width = {"info": 230, "poster": 370, "compact": 148}[card_style]
    text_x = cover_width + 88
    original = item.title if item.title != item_title(item) else ""
    blocks = [
        (label, 22, "accent", True, 0),
        (item_title(item), 38, "ink", True, 16),
    ]
    if original:
        blocks.append((original, 18, "muted", False, 4))
    blocks.append((primary, 26, "accent", True, 16))
    if secondary:
        blocks.append((secondary, 21, "muted", False, 6))
    blocks.append((item_tags(item), 18, "accent", False, 18))
    footer = "按排期提醒 · 临时改期以官方信息为准"
    natural_width = max(
        font(size, bold).getlength(line)
        for text, size, _, bold, _ in [*blocks, (footer, 16, "muted", False, 0)]
        for line in str(text).split("\n")
    )
    text_width = min(1200 - text_x - 60, max(400, ceil(natural_width)))
    width = text_x + text_width + 60
    # Use the same wrapped text metrics for sizing and drawing every block.
    bottom = 56
    positioned = []
    for text, size, color, bold, gap in blocks:
        bottom += gap
        positioned.append((text, size, color, bold, bottom))
        bottom += text_height(text, text_width, size, bold)
    footer_height = text_height(footer, text_width, 16)
    height = max(bottom + 24 + footer_height + 48, 96 + ceil(cover_width * 1.35))
    canvas = CardCanvas(width, height, card_theme)
    canvas.panel((28, 28, width - 28, height - 28))
    canvas.cover(covers.get(item.key), (48, 48, cover_width, height - 96))
    for text, size, color, bold, top in positioned:
        canvas.text(text_x, top, text, size, color, bold, width=text_width)
    canvas.text(text_x, height - 48 - footer_height, footer, 16, "muted", width=text_width)
    return canvas.save(output)
