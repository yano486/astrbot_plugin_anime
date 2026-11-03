from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Schedule:
    weekday: int
    hour: int
    minute: int
    raw_time: str
    source: str
    source_url: str = ""
    start_date: str = ""
    interval_days: int = 7
    timezone: str = "Asia/Tokyo"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Schedule":
        return cls(**value)


@dataclass
class SourceRecord:
    source: str
    title: str
    title_cn: str = ""
    bangumi_id: int | None = None
    aliases: list[str] = field(default_factory=list)
    season: str = ""
    item_type: str = "unknown"
    region: str = "unknown"
    genres: list[str] = field(default_factory=list)
    cover_url: str = ""
    detail_url: str = ""
    schedules: list[Schedule] = field(default_factory=list)
    source_url: str = ""
    season_role: str = "unknown"
    platform: str = ""
    studio: str = ""
    episode_count: int | None = None
    release_date: str = ""


@dataclass
class AnimeItem:
    key: str
    title: str
    title_cn: str = ""
    bangumi_id: int | None = None
    aliases: list[str] = field(default_factory=list)
    season: str = ""
    season_role: str = "unknown"
    item_type: str = "unknown"
    region: str = "unknown"
    genres: list[str] = field(default_factory=list)
    cover_url: str = ""
    detail_url: str = ""
    schedules: list[Schedule] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    source_urls: dict[str, str] = field(default_factory=dict)
    platforms: list[str] = field(default_factory=list)
    studios: list[str] = field(default_factory=list)
    episode_count: int | None = None
    release_date: str = ""
    data_status: str = "partial"
    schedule_note: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["schedules"] = [item.to_dict() for item in self.schedules]
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "AnimeItem":
        value = dict(value)
        value["schedules"] = [Schedule.from_dict(item) for item in value.get("schedules", [])]
        return cls(**value)


@dataclass
class Target:
    target_id: str
    display_name: str = ""
    platform: str = ""
    enabled: bool = True
    updated_at: str = ""
    whitelisted: bool = False
    subscribed: bool = False


@dataclass
class Subscription:
    target_id: str
    anime_key: str
    enabled: bool = True
    lead_minutes: int = 0
    on_time: bool = True


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

