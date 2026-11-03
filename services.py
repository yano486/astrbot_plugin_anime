from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from typing import Any

from .merge import merge_records, unify_schedules
from .sources import BangumiAdapter, BgmlistAdapter, SourceResult, YucAdapter


class RefreshService:
    def __init__(self, session: Any, store: Any, adapters: list[Any] | None = None, bangumi_token: str = ""):
        self.session = session
        self.store = store
        self.bangumi = BangumiAdapter(session, bangumi_token)
        self.adapters = adapters or [
            self.bangumi,
            BgmlistAdapter(session),
            YucAdapter(session),
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
                current.schedules, current.schedule_note = unify_schedules(current.schedules)
                if current.schedules:
                    current.data_status = "partial" if failed_sources.intersection(old.sources) else "ok"
                else:
                    current.data_status = "time_unknown"
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

    async def refresh_movies(self, today: date):
        result = await self.bangumi.fetch_movies(today)
        self.store.state["movie_source_status"] = {
            "bangumi": {
                "status": result.status,
                "error": result.error,
                "source_url": result.source_url,
                "fetched_at": result.fetched_at,
                "count": len(result.records),
            }
        }
        if result.status != "ok":
            self.store.save()
            return {"items": self.store.get_movie_items(), "sources": {"bangumi": result}, "updated_at": ""}
        items = [item for item in merge_records(result.records) if item.item_type in ("movie", "ova")]
        previous_by_key = {item.key: item for item in self.store.get_movie_items()}
        subscribed_keys = {sub.anime_key for sub in self.store.get_subscriptions() if sub.enabled}
        for item in items:
            if not item.release_date and item.key in previous_by_key:
                item.release_date = previous_by_key[item.key].release_date
        current_keys = {item.key for item in items}
        items.extend(
            previous_by_key[key]
            for key in subscribed_keys
            if key in previous_by_key and key not in current_keys
        )
        self.store.set_movie_items(items)
        self.store.state["movie_catalog_updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        last_year = today.year + (1 if today.month == 12 else 0)
        self.store.state["movie_catalog_scope"] = f"{today.year}-{last_year}"
        self.store.save()
        return {"items": items, "sources": {"bangumi": result}, "updated_at": self.store.state["movie_catalog_updated_at"]}

