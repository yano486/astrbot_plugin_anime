from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from .merge import merge_records
from .models import AnimeItem
from .sources import AcgSecretsAdapter, BangumiAdapter, BgmlistAdapter, SourceResult, YucAdapter, YourAnimesAdapter
from .push_tables import upcoming_movies
from datetime import date


class RefreshService:
    def __init__(self, session: Any, store: Any, adapters: list[Any] | None = None):
        self.session = session
        self.store = store
        self.bangumi = BangumiAdapter(session)
        self.adapters = adapters or [
            self.bangumi,
            BgmlistAdapter(session),
            YucAdapter(session),
            AcgSecretsAdapter(session),
            YourAnimesAdapter(session),
        ]

    async def refresh(self, season: str) -> dict[str, Any]:
        results: list[SourceResult] = await asyncio.gather(*(adapter.fetch(season) for adapter in self.adapters))
        records = [record for result in results if result.status == "ok" for record in result.records]
        items = merge_records(records)
        status = {
            result.source: {
                "status": result.status,
                "error": result.error,
                "source_url": result.source_url,
                "fetched_at": result.fetched_at,
                "count": len(result.records),
            }
            for result in results
        }
        if items:
            failed_sources = {name for name, value in status.items() if value["status"] == "error"}
            previous = self.store.get_items()
            new_by_key = {item.key: item for item in items}
            retained = []
            for old in previous:
                if old.season != season or not failed_sources.intersection(old.sources):
                    continue
                current = new_by_key.get(old.key)
                if current is None:
                    old.data_status = "partial" if old.data_status != "conflict" else old.data_status
                    retained.append(old)
                    continue
                for schedule in old.schedules:
                    if schedule.source in failed_sources and not any(
                        existing.source == schedule.source
                        and (existing.weekday, existing.hour, existing.minute) == (schedule.weekday, schedule.hour, schedule.minute)
                        for existing in current.schedules
                    ):
                        current.schedules.append(schedule)
                current.sources = sorted(set(current.sources) | (set(old.sources) & failed_sources))
                current.source_urls.update({key: value for key, value in old.source_urls.items() if key in failed_sources})
                if current.schedules and len({(s.weekday, s.hour, s.minute) for s in current.schedules}) > 1:
                    current.data_status = "conflict"
                elif failed_sources.intersection(old.sources) and current.data_status == "ok":
                    current.data_status = "partial"
            old_items = [item for item in previous if item.season != season]
            by_key = {item.key: item for item in old_items}
            by_key.update({item.key: item for item in items})
            by_key.update({item.key: item for item in retained})
            self.store.set_items(list(by_key.values()), status)
            self.store.state["season"] = season
            self.store.state["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        self.store.state["source_status"] = status
        self.store.save()
        return {"items": items, "sources": status, "updated_at": self.store.state.get("updated_at", "")}

    async def upcoming_movies(self, today: date, months: int = 3):
        result = await self.bangumi.fetch_movies(today, months)
        if result.status != "ok":
            return [], result
        items = merge_records(result.records)
        return upcoming_movies(items, today, months), result

