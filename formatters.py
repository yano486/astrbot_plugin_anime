from __future__ import annotations

from datetime import datetime

from .models import AnimeItem, Schedule
from .time_utils import jst_weekday_time_to_beijing

WEEKDAYS = ["", "一", "二", "三", "四", "五", "六", "日"]


def format_reminder(item: AnimeItem, schedule: Schedule, reminder_label: str = "即将播出") -> str:
    bj_day, bj_hour, bj_minute, _ = jst_weekday_time_to_beijing(schedule.weekday, schedule.hour, schedule.minute)
    day_text = WEEKDAYS[bj_day]
    title = item.title_cn or item.title
    source_text = "、".join(sorted(set(item.sources))) or schedule.source
    status = "（时间来源有冲突，仅供核对）" if item.data_status == "conflict" else "（按排期提醒，非实际上线确认）"
    return (
        f"📺 动画{reminder_label}\n{title}\n"
        f"北京时间：周{day_text} {bj_hour:02d}:{bj_minute:02d}\n"
        f"日本排期：周{WEEKDAYS[schedule.weekday]} {schedule.hour:02d}:{schedule.minute:02d} JST\n"
        f"数据来源：{source_text}{status}"
    )

