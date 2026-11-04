from __future__ import annotations

import re
import unicodedata
from collections import defaultdict

from .models import AnimeItem, SourceRecord, utc_now_iso
from .schedule_utils import schedule_sort_key
from ..sources.helpers import ADAPTATION_TYPE_ORDER, adaptation_types as extract_adaptation_types


_CJK_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def _cjk_number(value: str) -> str:
    if value.isdigit():
        return value
    if value == "十":
        return "10"
    if value.startswith("十"):
        return str(10 + _CJK_DIGITS.get(value[1:], 0))
    if value.endswith("十"):
        return str(_CJK_DIGITS.get(value[:-1], 0) * 10)
    if "十" in value:
        left, right = value.split("十", 1)
        return str(_CJK_DIGITS.get(left, 0) * 10 + _CJK_DIGITS.get(right, 0))
    if all(char in _CJK_DIGITS for char in value):
        return "".join(str(_CJK_DIGITS[char]) for char in value)
    return value


def normalize_title(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").lower()
    value = re.sub(
        r"第([0-9零〇一二两三四五六七八九十]+)(季|期|部)",
        lambda match: f"season{_cjk_number(match.group(1))}",
        value,
    )
    value = re.sub(r"(季|期|部)(?=$|[^\w\u4e00-\u9fff])", "season", value)
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


def _season_role(records: list[SourceRecord], season: str) -> str:
    declared = {record.season_role for record in records if record.season_role in {"new", "continuing"}}
    if "continuing" in declared:
        return "continuing"
    if "new" in declared:
        return "new"

    match = re.fullmatch(r"(\d{4})-(\d{2})", season or "")
    if not match:
        return "unknown"
    year, month = int(match.group(1)), int(match.group(2))
    season_start = f"{year}-{((month - 1) // 3) * 3 + 1:02d}-01"
    start_dates = [record.release_date[:10] for record in records if re.match(r"^\d{4}-\d{2}-\d{2}", record.release_date or "")]
    start_dates.extend(
        schedule.start_date[:10]
        for record in records
        for schedule in record.schedules
        if re.match(r"^\d{4}-\d{2}-\d{2}", schedule.start_date or "")
    )
    if not start_dates:
        return "unknown"
    return "continuing" if min(start_dates) < season_start else "new"


def unify_schedules(schedules: list, schedule_source: str = "earliest") -> tuple[list, str]:
    unique = []
    seen = set()
    for schedule in schedules:
        identity = (*schedule_sort_key(schedule), schedule.source)
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
    selected = min(unique, key=schedule_sort_key)
    if len({schedule_sort_key(schedule) for schedule in unique}) == 1:
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
        adaptations = set()
        platforms = set()
        studios = set()
        episode_counts = set()
        release_dates = set()
        for record in group:
            schedules.extend(record.schedules)
            aliases.update(record.aliases)
            aliases.update(filter(None, (record.title, record.title_cn)))
            genres.update(record.genres)
            adaptations.update(record.adaptation_types)
            adaptations.update(extract_adaptation_types(record.genres))
            if record.platform:
                platforms.add(record.platform)
            if record.studio:
                studios.add(record.studio)
            if record.episode_count:
                episode_counts.add(record.episode_count)
            if record.release_date:
                release_dates.add(record.release_date)
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
                season_role=_season_role(group, first.season),
                item_type=first.item_type,
                region=_region(group),
                genres=sorted(genres),
                adaptation_types=[value for value in ADAPTATION_TYPE_ORDER if value in adaptations],
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
