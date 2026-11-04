from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..core.models import SourceRecord


@dataclass
class SourceResult:
    source: str
    records: list[SourceRecord] = field(default_factory=list)
    source_url: str = ""
    status: str = "ok"
    error: str = ""
    fetched_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    )


class SourceAdapter:
    name = "source"

    def __init__(self, session: Any = None):
        self.session = session

    async def fetch(self, season: str) -> SourceResult:
        raise NotImplementedError

