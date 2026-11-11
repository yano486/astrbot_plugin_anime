from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from ..core.time_utils import BJ, JST
from .card_canvas import CardCanvas, header_layout, text_height


WEEKDAYS = "一二三四五六日"
DAY_COLORS = ("#83b8e7", "#7ccab3", "#d1b275", "#b6a2cf", "#dc9fac", "#78c3d0", "#a8c78a")


def _date(row, zone):
    if row.schedule is None and row.item.release_date:
        return date.fromisoformat(row.item.release_date[:10])
    return row.at.astimezone(zone).date()


def _time(row, zone):
    if row.schedule is None:
        return "上映 " + row.item.release_date[:10], "仅按日期提醒"
    local = row.at.astimezone(zone)
    other = row.at.astimezone(JST if zone.key == "Asia/Shanghai" else BJ)
    shift = "次日 " if other.date() > local.date() else "前日 " if other.date() < local.date() else ""
    other_label = "日本" if zone.key == "Asia/Shanghai" else "北京"
    return local.strftime("%H:%M"), other_label + " " + shift + other.strftime("%H:%M")


def render_swimlane(title, rows, output, timezone, *, theme="dark", covers=None, weekly=False):
    zone = ZoneInfo(timezone)
    covers = covers or {}
    grouped = {}
    for row in sorted(rows, key=lambda row: (row.at, row.item.title_cn or row.item.title)):
        grouped.setdefault(_date(row, zone), []).append(row)
    if weekly and grouped:
        monday = min(grouped)
        monday -= timedelta(days=monday.isoweekday() - 1)
        last = max(max(grouped), monday + timedelta(days=6))
        grouped = {monday + timedelta(days=i): grouped.get(monday + timedelta(days=i), []) for i in range((last - monday).days + 1)}

    margin, gap, label_width = 36, 14, 150
    columns = max(1, min(5, max((len(entries) for entries in grouped.values()), default=0)))
    # Remove unused column slots while keeping readable card and font sizes.
    width = max(720, 2400 - (5 - columns) * (418 + gap))
    content_x = margin + label_width + gap
    card_width = (width - margin * 2 - label_width - gap * columns - 16) // columns
    name_width = card_width - 118
    timezone_label = "北京时间" if timezone == "Asia/Shanghai" else "日本时间"
    caption = timezone_label
    if grouped:
        caption = min(grouped).strftime("%Y.%m.%d")
        if min(grouped) != max(grouped):
            caption += " — " + max(grouped).strftime("%m.%d")
        caption += " · " + timezone_label
    counts = {kind: len({row.item.key for row in rows if row.item.item_type == kind}) for kind in ("tv", "web", "movie", "ova")}
    type_names = {"tv": "TV", "web": "WEB", "movie": "剧场版", "ova": "OVA"}
    type_caption = " / ".join(f"{type_names[kind]} {count}" for kind, count in counts.items() if count)
    if type_caption:
        caption += " · " + type_caption
    plan = []
    _, divider_y = header_layout(title, caption, width)
    content_top = divider_y + 26
    y = content_top
    for day, entries in grouped.items():
        grid = []
        grid_y = y + 16
        for index in range(0, len(entries), columns):
            batch = entries[index:index + columns]
            height = max(max(144, 82 + text_height(row.item.title_cn or row.item.title, name_width, 22, True)) for row in batch)
            grid.append((batch, grid_y, height))
            grid_y += height + gap
        band_height = max(162, grid_y - y + 2)
        plan.append((day, entries, y, band_height, grid))
        y += band_height + gap
    if not plan:
        y += 110

    canvas = CardCanvas(width, y + 100, theme)
    canvas.header(title, caption, len({row.item.key for row in rows}))
    today = datetime.now(zone).date()
    for day, entries, top, height, grid in plan:
        current = day == today
        canvas.panel((margin, top, width - margin, top + height), "soft" if current else "panel", 12)
        accent = canvas.colors["accent"] if current or theme == "light" else DAY_COLORS[day.isoweekday() - 1]
        if current:
            canvas.draw.rounded_rectangle((margin, top, width - margin, top + height), radius=12, outline=accent, width=2)
        canvas.draw.rounded_rectangle((margin, top + 8, margin + 5, top + height - 8), radius=2, fill=accent)
        canvas.text(margin + 22, top + 24, "周" + WEEKDAYS[day.isoweekday() - 1], 27, "accent", True, width=label_width - 22)
        canvas.text(margin + 22, top + 66, day.strftime("%m.%d"), 20, "muted", width=label_width - 22)
        canvas.text(margin + 22, top + 101, f"{len(entries)} 部" + (" · 今天" if current else ""), 16, "muted", width=label_width - 20)
        for batch, row_y, row_height in grid:
            for index, row in enumerate(batch):
                x = content_x + index * (card_width + gap)
                canvas.panel((x, row_y, x + card_width, row_y + row_height), "soft")
                canvas.cover(covers.get(row.item.key), (x + 12, row_y + 14, 80, 114))
                bottom = canvas.text(x + 106, row_y + 12, row.item.title_cn or row.item.title, 22, bold=True, width=name_width)
                primary, secondary = _time(row, zone)
                bottom = canvas.text(x + 106, bottom + 5, primary, 23, "accent", True, width=name_width)
                canvas.text(x + 106, bottom + 2, secondary, 15, "muted", width=name_width)
        if not entries:
            canvas.text(content_x + 20, top + 60, "暂无订阅排期", 21, "muted")
    if not plan:
        canvas.text(margin + 20, content_top + 30, "这段时间没有已知订阅排期。", 26, "muted")
    canvas.footer(y + 12)
    return canvas.save(output)
