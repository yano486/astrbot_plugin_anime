from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from ..core.models import AnimeItem, Schedule
from ..core.time_utils import schedule_time_in_timezone

WEEKDAYS = ["", "一", "二", "三", "四", "五", "六", "日"]


def format_reminder(
    item: AnimeItem,
    schedule: Schedule,
    reminder_label: str = "即将播出",
    display_timezone: str = "Asia/Shanghai",
) -> str:
    bj_day, bj_hour, bj_minute = schedule_time_in_timezone(schedule, "Asia/Shanghai")
    jst_day, jst_hour, jst_minute = schedule_time_in_timezone(schedule, "Asia/Tokyo")
    title = item.title_cn or item.title
    source_text = "、".join(sorted(set(item.sources))) or schedule.source
    status = "（按最早来源时间统一排期，非实际上线确认）" if item.schedule_note else "（按排期提醒，非实际上线确认）"
    times = {
        "Asia/Shanghai": f"北京时间：周{WEEKDAYS[bj_day]} {bj_hour:02d}:{bj_minute:02d}",
        "Asia/Tokyo": f"日本时间：周{WEEKDAYS[jst_day]} {jst_hour:02d}:{jst_minute:02d}",
    }
    secondary = "Asia/Tokyo" if display_timezone == "Asia/Shanghai" else "Asia/Shanghai"
    return (
        f"📺 动画{reminder_label}\n{title}\n"
        f"{times[display_timezone]}\n{times[secondary]}\n"
        f"数据来源：{source_text}{status}"
    )


def format_movie_reminder(
    item: AnimeItem,
    occurrence: datetime | None,
    reminder_label: str,
    date_only: bool = False,
    display_timezone: str = "Asia/Shanghai",
) -> str:
    title = item.title_cn or item.title
    zone_label = "北京时间" if display_timezone == "Asia/Shanghai" else "日本时间"
    if occurrence and date_only:
        release_text = occurrence.astimezone(ZoneInfo(display_timezone)).strftime("%Y-%m-%d")
        precision = "（仅按上映日期提醒，不代表具体上映时刻）"
    elif occurrence:
        release_text = occurrence.astimezone(ZoneInfo(display_timezone)).strftime("%Y-%m-%d %H:%M")
        precision = ""
    else:
        release_text = "时间待定"
        precision = ""
    return (
        f"🎬 {item.item_type.upper()} {reminder_label}\n{title}\n"
        f"上映日期：{zone_label} {release_text}{precision}\n"
        f"数据来源：{'、'.join(item.sources) or 'Bangumi'}"
    )

