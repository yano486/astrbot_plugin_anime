from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from ..core.time_utils import BJ, JST, schedule_time_in_timezone
from .card_canvas import CardCanvas, text_height


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


def row_times(row, timezone):
    if row.schedule is None:
        return "上映日期", row.item.release_date[:10] or row.at.strftime("%Y-%m-%d")
    local = row.at.astimezone(ZoneInfo(timezone))
    other_zone = JST if timezone == "Asia/Shanghai" else BJ
    other = row.at.astimezone(other_zone)
    prefix = "次日 " if other.date() > local.date() else "前日 " if other.date() < local.date() else ""
    label = "日本" if timezone == "Asia/Shanghai" else "北京"
    return local.strftime("%H:%M"), label + " " + prefix + other.strftime("%H:%M")


def row_height(row, width, style, weekly):
    title_size = 24 if weekly else 27
    if style == "poster":
        return 250 + text_height(item_title(row.item), width - 40, title_size, True) + 96 + text_height(item_tags(row.item), width - 40, 16)
    cover_width = 64 if style == "compact" else 86 if weekly else 110
    text_width = width - cover_width - (190 if not weekly else 56)
    height = 18 + text_height(item_title(row.item), text_width, title_size, True)
    if weekly:
        height += 8 + 37 + 25
    elif row.item.title != item_title(row.item):
        height += 4 + text_height(row.item.title, text_width, 16)
    height += 8 + text_height(item_tags(row.item), text_width, 16) + 18
    return max(146 if weekly else 180, height)


def draw_row(canvas, row, x, y, width, height, style, timezone, covers, weekly=False):
    canvas.panel((x, y, x + width, y + height))
    item = row.item
    clock, secondary = row_times(row, timezone)
    size = 24 if weekly else 27
    if style == "poster":
        canvas.cover(covers.get(item.key), (x + 12, y + 12, width - 24, 224))
        text_x, text_y, text_width = x + 20, y + 250, width - 40
    else:
        cover_width = 64 if style == "compact" else 86 if weekly else 110
        canvas.cover(covers.get(item.key), (x + 16, y + 18, cover_width, 110 if style == "compact" else 120 if weekly else 144))
        text_x, text_y = x + cover_width + 34, y + 18
        text_width = width - cover_width - (190 if not weekly else 56)
    bottom = canvas.text(text_x, text_y, item_title(item), size, bold=True, width=text_width)
    if not weekly and style != "poster":
        if item.title != item_title(item):
            bottom = canvas.text(text_x, bottom + 4, item.title, 16, "muted", width=text_width)
        canvas.text(x + width - 138, y + 26, clock, 26, "accent", True, width=124)
        canvas.text(x + width - 138, y + 70, secondary, 16, "muted", width=122)
    else:
        bottom = canvas.text(text_x, bottom + 8, clock, 28, "accent", True, width=text_width)
        bottom = canvas.text(text_x, bottom, secondary, 16, "muted", width=text_width)
    canvas.text(text_x, bottom + 8, item_tags(item), 16, "accent", width=text_width)


def render_table(title, rows, output, timezone="Asia/Shanghai", *, card_style="info", card_theme="dark", covers=None, weekly=False):
    validate_style(card_style)
    covers = covers or {}
    zone = ZoneInfo(timezone)
    by_day = {}
    for row in sorted(rows, key=lambda row: (row.at, item_title(row.item))):
        day = date.fromisoformat(row.item.release_date[:10]) if row.schedule is None and row.item.release_date else row.at.astimezone(zone).date()
        by_day.setdefault(day, []).append(row)
    if weekly and by_day:
        start = min(by_day)
        start -= timedelta(days=start.isoweekday() - 1)
        by_day = {start + timedelta(days=i): by_day.get(start + timedelta(days=i), []) for i in range(7)}
    if weekly and card_style == "poster" and by_day:
        return render_poster_week(title, by_day, output, timezone, card_theme, covers)
    margin, gap = 36, 14
    plan = []
    y = 204
    for day, entries in by_day.items():
        band = weekly and card_style == "compact"
        columns = 3 if band else 2 if weekly or card_style == "poster" else 1
        left = 160 if band else margin
        width = (1200 - margin - left - gap * (columns - 1)) // columns
        group_start = y
        if not band:
            y += 52
        for index in range(0, len(entries), columns):
            batch = entries[index:index + columns]
            # Each grid row uses its tallest item; titles are never cropped to a fixed line count.
            height = max(row_height(row, width, card_style, weekly) for row in batch)
            plan.append(("rows", batch, left, y, width, height, card_style))
            y += height + gap
        if not entries:
            y += 130 if band else 52
        plan.append(("day", day, entries, group_start, y - group_start, band))
        y += 16
    if not by_day:
        y += 100
    canvas = CardCanvas(1200, y + 100, card_theme)
    label = "北京时间" if timezone == "Asia/Shanghai" else "日本时间"
    caption = label
    if by_day:
        first, last = min(by_day), max(by_day)
        caption = first.strftime("%Y.%m.%d") + (" — " + last.strftime("%m.%d") if first != last else "") + " · " + label
    canvas.header(title, caption, len({row.item.key for row in rows}))
    for instruction in plan:
        if instruction[0] == "day":
            _, day, entries, top, height, band = instruction
            name = "周" + WEEKDAYS[day.isoweekday() - 1]
            if band:
                canvas.panel((36, top, 146, top + height), "soft")
                canvas.text(52, top + 14, name, 24, "accent", True, width=86)
                canvas.text(52, top + 55, day.strftime("%m.%d"), 18, "muted", width=86)
                canvas.text(52, top + 88, f"{len(entries)} 部", 16, "muted", width=86)
            else:
                canvas.text(36, top, name + "  " + day.strftime("%m.%d"), 24, "accent", True)
            if not entries:
                canvas.text(180 if band else 52, top + (18 if band else 48), "暂无订阅排期", 18, "muted")
        else:
            _, batch, left, top, width, height, style = instruction
            for col, row in enumerate(batch):
                draw_row(canvas, row, left + col * (width + gap), top, width, height, style, timezone, covers, weekly)
    if not by_day:
        canvas.text(50, 234, "这段时间没有已知排期。", 26, "muted")
    canvas.footer(y + 12)
    return canvas.save(output)


def render_poster_week(title, groups, output, timezone, theme, covers):
    width, gap = 557, 14
    plan = []
    y = 204
    days = list(groups)
    for index in range(0, len(days), 2):
        pair = days[index:index + 2]
        heights = {}
        for day in pair:
            heights[day] = [max(144, 20 + text_height(item_title(row.item), width - 158, 24, True) + 37 + 25) for row in groups[day]]
        block_height = max(130, max(90 + sum(values) for values in heights.values()))
        for col, day in enumerate(pair):
            plan.append((36 + col * (width + gap), y, day, heights[day], block_height))
        y += block_height + gap
    canvas = CardCanvas(1200, y + 100, theme)
    caption = f"{days[0]:%Y.%m.%d} — {days[-1]:%m.%d} · " + ("北京时间" if timezone == "Asia/Shanghai" else "日本时间")
    canvas.header(title, caption, len({row.item.key for entries in groups.values() for row in entries}))
    for x, top, day, heights, height in plan:
        canvas.panel((x, top, x + width, top + height))
        canvas.text(x + 20, top + 18, f"周{WEEKDAYS[day.isoweekday() - 1]}  {day:%m.%d}", 24, "accent", True, width=width - 40)
        row_y = top + 72
        for row, row_h in zip(groups[day], heights):
            canvas.cover(covers.get(row.item.key), (x + 20, row_y, 92, 126))
            bottom = canvas.text(x + 132, row_y, item_title(row.item), 24, bold=True, width=width - 158)
            primary, secondary = row_times(row, timezone)
            bottom = canvas.text(x + 132, bottom + 8, primary, 28, "accent", True, width=width - 158)
            canvas.text(x + 132, bottom, secondary, 16, "muted", width=width - 158)
            row_y += row_h
        if not groups[day]:
            canvas.text(x + 20, row_y, "暂无订阅排期", 18, "muted", width=width - 40)
    canvas.footer(y + 12)
    return canvas.save(output)


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
    text_width = 1200 - text_x - 60
    name_height = text_height(item_title(item), text_width, 38, True)
    original = item.title if item.title != item_title(item) else ""
    original_height = text_height(original, text_width, 18) if original else 0
    height = max(480 if card_style == "info" else 620 if card_style == "poster" else 390, 300 + name_height + original_height + text_height(item_tags(item), text_width, 18))
    canvas = CardCanvas(1200, height, card_theme)
    canvas.panel((28, 28, 1172, height - 28))
    canvas.cover(covers.get(item.key), (48, 48, cover_width, height - 96))
    bottom = canvas.text(text_x, 56, label, 22, "accent", True, width=text_width)
    bottom = canvas.text(text_x, bottom + 16, item_title(item), 38, bold=True, width=text_width)
    if original:
        bottom = canvas.text(text_x, bottom + 4, original, 18, "muted", width=text_width)
    bottom = canvas.text(text_x, bottom + 16, primary, 26, "accent", True, width=text_width)
    if secondary:
        bottom = canvas.text(text_x, bottom + 6, secondary, 21, "muted", width=text_width)
    canvas.text(text_x, bottom + 18, item_tags(item), 18, "accent", width=text_width)
    canvas.text(text_x, height - 78, "按排期提醒 · 临时改期以官方信息为准", 16, "muted", width=text_width)
    return canvas.save(output)
