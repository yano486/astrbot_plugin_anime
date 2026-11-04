from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
import re
import time as clock
from stat import S_ISREG
from typing import Iterable
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

from ..core.models import AnimeItem, Schedule
from ..core.time_utils import BJ, JST


_GENERATED_TABLE_NAME = re.compile(r"[0-9a-f]{32}\.png\Z")


@dataclass(frozen=True)
class Airing:
    item: AnimeItem
    schedule: Schedule | None
    at: datetime


def cleanup_generated_tables(
    directory: Path,
    *,
    now: float | None = None,
    retention_seconds: float = 7 * 86400,
) -> int:
    root = Path(directory)
    if root.is_symlink() or not root.is_dir():
        return 0
    cutoff = (clock.time() if now is None else now) - max(0, retention_seconds)
    removed = 0
    for path in root.iterdir():
        if not _GENERATED_TABLE_NAME.fullmatch(path.name):
            continue
        try:
            file_stat = path.lstat()
        except FileNotFoundError:
            continue
        if S_ISREG(file_stat.st_mode) and file_stat.st_mtime < cutoff:
            path.unlink()
            removed += 1
    return removed


def _first_occurrence(schedule: Schedule) -> datetime | None:
    if not schedule.start_date:
        return None
    try:
        day = date.fromisoformat(schedule.start_date[:10])
    except ValueError:
        return None
    offset, minutes = divmod(schedule.hour * 60 + schedule.minute, 24 * 60)
    local = datetime.combine(day + timedelta(days=offset), time(minutes // 60, minutes % 60), JST)
    return local.astimezone(BJ)


def airings_between(items: Iterable[AnimeItem], start: datetime, end: datetime) -> list[Airing]:
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start and end must be timezone-aware")
    start, end = start.astimezone(BJ), end.astimezone(BJ)
    rows: dict[tuple[str, datetime], Airing] = {}
    for item in items:
        if item.item_type in ("movie", "ova"):
            continue
        for schedule in item.schedules:
            first = _first_occurrence(schedule)
            if first is None:
                # Date-less weekly records can still be placed into the requested calendar window.
                local_start = start.astimezone(JST)
                day_offset = (schedule.weekday - local_start.isoweekday()) % 7
                candidate_day = local_start.date() + timedelta(days=day_offset)
                local_minutes = (schedule.hour % 24) * 60 + schedule.minute
                jst_dt = datetime.combine(candidate_day, time(local_minutes // 60, local_minutes % 60), JST)
                if schedule.hour >= 24:
                    jst_dt += timedelta(days=schedule.hour // 24)
                first = jst_dt.astimezone(BJ)
                interval = max(1, schedule.interval_days or 7)
                while first < start:
                    first += timedelta(days=interval)
                candidate = first
                while candidate < end:
                    rows[(item.key, candidate)] = Airing(item, schedule, candidate)
                    candidate += timedelta(days=interval)
                continue
            interval = max(1, schedule.interval_days or 7)
            candidate = first
            if candidate < start:
                steps = max(0, (start.date() - candidate.date()).days // interval)
                candidate += timedelta(days=steps * interval)
                while candidate < start:
                    candidate += timedelta(days=interval)
            while candidate < end:
                rows[(item.key, candidate)] = Airing(item, schedule, candidate)
                candidate += timedelta(days=interval)
    return sorted(rows.values(), key=lambda row: (row.at, row.item.title_cn or row.item.title))


def upcoming_movies(items: Iterable[AnimeItem], today: date) -> list[Airing]:
    last_year = today.year + (1 if today.month == 12 else 0)
    rows = []
    for item in items:
        if item.item_type not in ("movie", "ova") or item.region not in ("jp", "mixed") or not item.release_date:
            continue
        try:
            release = date.fromisoformat(item.release_date[:10])
        except ValueError:
            continue
        if today <= release and release.year <= last_year:
            rows.append(Airing(item, None, datetime.combine(release, time.min, BJ)))
    return sorted(rows, key=lambda row: (row.at, row.item.title_cn or row.item.title))


def _font(size: int, bold: bool = False):
    candidates = (
        [
            r"C:\Windows\Fonts\msyhbd.ttc",
            "/system/fonts/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        ]
        if bold
        else [
            r"C:\Windows\Fonts\msyh.ttc",
            "/system/fonts/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        ]
    )
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def render_airings_image(title: str, rows: list[Airing], output: Path, display_timezone: str = "Asia/Shanghai") -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    width, margin = 1200, 64
    row_height = 78
    groups: list[tuple[str, list[Airing]]] = []
    for row in rows:
        if row.schedule is None and row.item.release_date:
            try:
                label = date.fromisoformat(row.item.release_date[:10]).strftime("%m月%d日 %A")
            except ValueError:
                label = row.item.release_date[:10]
        else:
            display_at = row.at.astimezone(ZoneInfo(display_timezone))
            label = display_at.strftime("%m月%d日 %A") if row.schedule is None else display_at.strftime("%m月%d日")
        if not groups or groups[-1][0] != label:
            groups.append((label, []))
        groups[-1][1].append(row)
    height = 285 + max(1, len(rows)) * row_height + len(groups) * 34 + 80
    image = Image.new("RGB", (width, height), "#f3f1e9")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width, 13), fill="#d66043")
    draw.text((margin, 50), "ANIME / SCHEDULE", font=_font(18, True), fill="#65806c")
    draw.text((margin, 87), title, font=_font(48, True), fill="#1c2d2b")
    timezone_label = "北京时间" if display_timezone == "Asia/Shanghai" else "日本时间"
    draw.text((margin, 157), f"{timezone_label}  ·  共 {len(rows)} 部", font=_font(20), fill="#62716b")
    draw.line((margin, 212, width - margin, 212), fill="#cbd1c6", width=2)
    if not rows:
        draw.text((margin, 270), "这段时间没有已知排期。", font=_font(28), fill="#5a6963")
    y = 235
    for label, grouped in groups:
        draw.text((margin, y), label, font=_font(19, True), fill="#d15c41")
        y += 34
        for row in grouped:
            item, schedule = row.item, row.schedule
            display_at = row.at.astimezone(ZoneInfo(display_timezone))
            time_text = display_at.strftime("%H:%M") if row.schedule is not None else "上映"
            draw.rounded_rectangle((margin, y, width - margin, y + 64), radius=10, fill="#fffefa", outline="#d9ded4", width=1)
            draw.text((margin + 18, y + 16), time_text, font=_font(23, True), fill="#334e41")
            draw.text((margin + 150, y + 14), item.title_cn or item.title, font=_font(21, True), fill="#202e2b")
            detail = item.title if item.title_cn and item.title_cn != item.title else ""
            if schedule:
                detail = f"{detail}   日本时间 {schedule.hour:02d}:{schedule.minute:02d} JST   来源：{'、'.join(item.sources)}".strip()
            else:
                detail = f"{detail}   {'OVA' if item.item_type == 'ova' else '剧场版'} / 上映日期".strip()
            draw.text((margin + 150, y + 40), detail[:76], font=_font(14), fill="#78847d")
            y += row_height
    footer_y = height - 52
    draw.line((margin, footer_y - 14, width - margin, footer_y - 14), fill="#d6dbd2", width=1)
    draw.text((margin, footer_y), "排期来自公开资料，仅供参考；临时改期或延期以官方公告为准。", font=_font(13), fill="#818c85")
    image.save(output, format="PNG", optimize=True)
    return output


def render_weekly_image(title: str, rows: list[Airing], output: Path, display_timezone: str = "Asia/Shanghai") -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    width, margin = 1800, 44
    label_width, gap, card_width, card_height = 138, 12, 190, 86
    columns = 8
    start_y = 230
    by_day: dict[date, list[Airing]] = {}
    for row in rows:
        by_day.setdefault(row.at.astimezone(ZoneInfo(display_timezone)).date(), []).append(row)
    days = sorted(by_day)
    day_heights = [max(116, 58 + ((len(by_day[day]) + columns - 1) // columns) * (card_height + 9)) for day in days]
    height = start_y + sum(day_heights) + 75
    image = Image.new("RGB", (width, height), "#0d0d18")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((24, 20, width - 24, 145), radius=22, fill="#151522", outline="#29293a", width=2)
    draw.text((margin + 4, 44), "ANIME / WEEKLY GRID", font=_font(17, True), fill="#68cbd4")
    draw.text((margin, 76), title, font=_font(42, True), fill="#f3f1f6")
    timezone_label = "北京时间" if display_timezone == "Asia/Shanghai" else "日本时间"
    draw.text((margin, 137), f"{timezone_label} · 共 {len(rows)} 部 · 按星期分区", font=_font(17), fill="#9c9daf")
    draw.text((width - 280, 57), f"{len(days)} 个播放日", font=_font(20, True), fill="#70d3bd")
    accents = ["#4ca1f2", "#47d77a", "#f2ad2f", "#c748dd", "#f04464", "#26c8d2", "#63dd37"]
    y = start_y
    for index, day in enumerate(days):
        entries = sorted(by_day[day], key=lambda row: (row.at, row.item.title_cn or row.item.title))
        band_height = day_heights[index]
        accent = accents[day.isoweekday() - 1]
        draw.rounded_rectangle((24, y, width - 24, y + band_height - 8), radius=18, fill="#12121d", outline="#242436", width=1)
        draw.rounded_rectangle((24, y, 31, y + band_height - 8), radius=3, fill=accent)
        weekday_label = ["", "周一", "周二", "周三", "周四", "周五", "周六", "周日"][day.isoweekday()]
        draw.text((margin, y + 15), weekday_label, font=_font(21, True), fill="#f1eff5")
        draw.text((margin, y + 46), day.strftime("%m/%d"), font=_font(17, True), fill=accent)
        draw.text((margin, y + 72), f"{len(entries)} 部", font=_font(14), fill="#9b9cac")
        for item_index, row in enumerate(entries):
            col, line = item_index % columns, item_index // columns
            x = margin + label_width + col * (card_width + gap)
            card_y = y + 12 + line * (card_height + 9)
            draw.rounded_rectangle((x, card_y, x + card_width, card_y + card_height), radius=11, fill="#191927", outline="#323246", width=1)
            display_at = row.at.astimezone(ZoneInfo(display_timezone))
            draw.text((x + 10, card_y + 8), display_at.strftime("%H:%M"), font=_font(14, True), fill="#50cad5")
            name = row.item.title_cn or row.item.title
            draw.text((x + 10, card_y + 30), name[:13], font=_font(15, True), fill="#eceaf1")
            if row.schedule:
                jst = f"日本 {row.schedule.hour:02d}:{row.schedule.minute:02d}"
            else:
                jst = "OVA / 剧场版"
            draw.text((x + 10, card_y + 58), jst, font=_font(11), fill="#aaaabc")
        y += band_height
    draw.text((margin, height - 42), "排期来自公开资料，仅供参考；临时改期或延期以官方公告为准。", font=_font(13), fill="#77788a")
    image.save(output, format="PNG", optimize=True)
    return output


def render_notification_card(item: AnimeItem, mode: str, output: Path, display_timezone: str = "Asia/Shanghai") -> Path:
    if mode not in {"reminder", "update"}:
        raise ValueError("mode must be reminder or update")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    width, height = 1000, 520
    image = Image.new("RGB", (width, height), "#101b1a")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((24, 24, width - 24, height - 24), radius=26, fill="#162522", outline="#3a574b", width=2)
    draw.rectangle((24, 24, width - 24, 34), fill="#d66043")
    title = item.title_cn or item.title
    label = "动画开播提醒" if mode == "reminder" else "动画更新卡片"
    draw.text((64, 70), "ANIME / SCHEDULE", font=_font(17, True), fill="#85b59a")
    draw.text((64, 108), label, font=_font(36, True), fill="#f3f1e9")
    draw.text((64, 183), title[:28], font=_font(42, True), fill="#ffffff")
    if item.schedules:
        schedule = item.schedules[0]
        offset = -60 if display_timezone == "Asia/Shanghai" else 0
        total = schedule.hour * 60 + schedule.minute + offset
        day_shift, minutes = divmod(total, 24 * 60)
        weekday = ((schedule.weekday - 1 + day_shift) % 7) + 1
        weekday_text = "\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u65e5"[weekday - 1]
        date_text = f"\u6bcf\u5468{weekday_text} {minutes // 60:02d}:{minutes % 60:02d}"
    elif item.release_date:
        date_text = item.release_date[:10]
    else:
        date_text = "时间待定"
    zone_label = "北京时间" if display_timezone == "Asia/Shanghai" else "日本时间"
    draw.text((64, 275), f"{zone_label}  {date_text}", font=_font(30, True), fill="#e7b978")
    if item.title and item.title != title:
        draw.text((64, 333), item.title[:52], font=_font(20), fill="#a9b8ad")
    sources = "、".join(item.sources) or "Bangumi / YUC / bgmlist"
    draw.text((64, 405), f"数据来源：{sources}"[:72], font=_font(17), fill="#a9b8ad")
    draw.line((64, 452, width - 64, 452), fill="#354941", width=1)
    draw.text((64, 468), "排期仅供参考；临时调整以官方信息为准。", font=_font(14), fill="#778b80")
    image.save(output, format="PNG", optimize=True)
    return output
