from __future__ import annotations

from datetime import datetime

from .models import AnimeItem, Schedule
from .time_utils import BJ, jst_weekday_time_to_beijing

WEEKDAYS = ["", "一", "二", "三", "四", "五", "六", "日"]


def format_reminder(item: AnimeItem, schedule: Schedule, reminder_label: str = "即将播出") -> str:
    bj_day, bj_hour, bj_minute, _ = jst_weekday_time_to_beijing(schedule.weekday, schedule.hour, schedule.minute)
    day_text = WEEKDAYS[bj_day]
    title = item.title_cn or item.title
    source_text = "、".join(sorted(set(item.sources))) or schedule.source
    status = "（按最早来源时间统一排期，非实际上线确认）" if item.schedule_note else "（按排期提醒，非实际上线确认）"
    return (
        f"📺 动画{reminder_label}\n{title}\n"
        f"北京时间：周{day_text} {bj_hour:02d}:{bj_minute:02d}\n"
        f"日本排期：周{WEEKDAYS[schedule.weekday]} {schedule.hour:02d}:{schedule.minute:02d} JST\n"
        f"数据来源：{source_text}{status}"
    )


def format_movie_reminder(item: AnimeItem, occurrence: datetime | None, reminder_label: str, date_only: bool = False) -> str:
    title = item.title_cn or item.title
    release_text = occurrence.astimezone(BJ).strftime("%Y-%m-%d %H:%M") if occurrence else "时间待定"
    precision = "（来源只有日期，按北京时间 00:00 作为提醒时间；可在 WebUI 设置具体上映时间）" if date_only else ""
    return (
        f"🎬 {item.item_type.upper()} {reminder_label}\n{title}\n"
        f"上映时间：北京时间 {release_text}{precision}\n"
        f"数据来源：{'、'.join(item.sources) or 'Bangumi'}"
    )

