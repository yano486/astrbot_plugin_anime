from __future__ import annotations

import re
import unicodedata
from collections import defaultdict

from .models import AnimeItem, SourceRecord, utc_now_iso


def normalize_title(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").lower()
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", value)


def _region(records: list[SourceRecord]) -> str:
    regions = {record.region for record in records if record.region != "unknown"}
    if not regions:
        return "unknown"
    if len(regions) == 1:
        return next(iter(regions))
    if "jp" in regions:
        return "mixed"
    return "foreign"


def _status(schedules: list) -> str:
    if not schedules:
        return "time_unknown"
    return "ok"


def _schedule_key(schedule) -> tuple[int, int]:
    day_offset, clock_minutes = divmod(schedule.hour * 60 + schedule.minute, 24 * 60)
    weekday = (schedule.weekday - 1 + day_offset) % 7
    return weekday, clock_minutes


def unify_schedules(schedules: list, schedule_source: str = "earliest") -> tuple[list, str]:
    unique = []
    seen = set()
    for schedule in schedules:
        identity = (*_schedule_key(schedule), schedule.source)
        if identity not in seen:
            unique.append(schedule)
            seen.add(identity)
    if schedule_source != "earliest":
        selected_source = [schedule for schedule in unique if schedule.source == schedule_source]
        if not selected_source:
            if unique:
                note = (
                    "Bangumi 当前数据不含具体播出时刻，已按设置暂停时间提醒"
                    if schedule_source == "bangumi"
                    else f"当前选择的排期来源 {schedule_source} 暂无播出时刻，已暂停时间提醒"
                )
                return [], note
            return [], ""
        unique = selected_source
    if not unique:
        return [], ""
    selected = min(unique, key=_schedule_key)
    if len({_schedule_key(schedule) for schedule in unique}) == 1:
        return [selected], ""
    alternatives = "、".join(
        f"{schedule.source} {schedule.hour:02d}:{schedule.minute:02d} JST"
        for schedule in unique
        if schedule is not selected
    )
    note = (
        f"来源时间不一致，已统一采用最早时间 "
        f"{selected.hour:02d}:{selected.minute:02d} JST（{selected.source}）；"
        f"其他来源：{alternatives}"
    )
    return [selected], note


def merge_records(records: list[SourceRecord], schedule_source: str = "earliest") -> list[AnimeItem]:
    groups: list[list[SourceRecord]] = []
    by_id: dict[int, list[SourceRecord]] = defaultdict(list)
    by_title: dict[str, list[SourceRecord]] = defaultdict(list)
    for record in records:
        if record.bangumi_id is not None:
            by_id[record.bangumi_id].append(record)
        else:
            by_title[normalize_title(record.title_cn or record.title)].append(record)

    groups.extend(by_id.values())
    unmatched: dict[str, list[SourceRecord]] = defaultdict(list)
    for title_records in by_title.values():
        for record in title_records:
            aliases = {normalize_title(value) for value in [record.title, record.title_cn, *record.aliases] if value}
            candidates = []
            for group in groups:
                group_aliases = {
                    normalize_title(value)
                    for current in group
                    for value in [current.title, current.title_cn, *current.aliases]
                    if value
                }
                if aliases & group_aliases:
                    candidates.append(group)
            if len(candidates) == 1:
                candidates[0].append(record)
            else:
                canonical = normalize_title(record.title_cn or record.title)
                if canonical:
                    unmatched[canonical].append(record)
    groups.extend(unmatched.values())

    result: list[AnimeItem] = []
    for group in groups:
        first = group[0]
        schedules = []
        source_urls: dict[str, str] = {}
        aliases = set()
        genres = set()
        platforms = set()
        studios = set()
        episode_counts = set()
        release_dates = set()
        roles = set()
        for record in group:
            schedules.extend(record.schedules)
            aliases.update(record.aliases)
            aliases.update(filter(None, (record.title, record.title_cn)))
            genres.update(record.genres)
            if record.platform:
                platforms.add(record.platform)
            if record.studio:
                studios.add(record.studio)
            if record.episode_count:
                episode_counts.add(record.episode_count)
            if record.release_date:
                release_dates.add(record.release_date)
            if record.season_role != "unknown":
                roles.add(record.season_role)
            if record.source_url:
                source_urls[record.source] = record.source_url
        unique_schedules, schedule_note = unify_schedules(schedules, schedule_source)
        key = f"bangumi:{first.bangumi_id}" if first.bangumi_id is not None else f"title:{normalize_title(first.title)}"
        result.append(
            AnimeItem(
                key=key,
                title=first.title,
                title_cn=first.title_cn,
                bangumi_id=first.bangumi_id,
                aliases=sorted(aliases),
                season=first.season,
                season_role="continuing" if "continuing" in roles else ("new" if "new" in roles else "unknown"),
                item_type=first.item_type,
                region=_region(group),
                genres=sorted(genres),
                cover_url=first.cover_url,
                detail_url=first.detail_url,
                schedules=unique_schedules,
                sources=sorted({record.source for record in group}),
                source_urls=source_urls,
                platforms=sorted(platforms),
                studios=sorted(studios),
                episode_count=next(iter(episode_counts)) if len(episode_counts) == 1 else None,
                release_date=next(iter(release_dates)) if len(release_dates) == 1 else "",
                data_status=_status(unique_schedules),
                schedule_note=schedule_note,
                updated_at=utc_now_iso(),
            )
        )
    return sorted(result, key=lambda item: (item.season, item.title_cn or item.title))
