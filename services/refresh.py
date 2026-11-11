from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from typing import Any, Awaitable, Callable, Hashable

from ..core.diagnostics import get_plugin_logger
from ..core.merge import merge_records, unify_schedules
from ..sources import BangumiAdapter, BgmlistAdapter, SourceResult, YucAdapter


logger = get_plugin_logger()


class RefreshService:
    def __init__(self, session: Any, store: Any, adapters: list[Any] | None = None, bangumi_token: str = "", bangumi_proxy: Any = ""):
        self.session = session
        self.store = store
        self.bangumi = BangumiAdapter(session, bangumi_token, bangumi_proxy)
        self.adapters = adapters or [
            self.bangumi,
            BgmlistAdapter(session),
            YucAdapter(session),
        ]
        self._inflight: dict[tuple[str, Hashable], asyncio.Task[Any]] = {}

    async def refresh(self, season: str) -> dict[str, Any]:
        return await self._singleflight(("season", season), lambda: self._refresh(season))

    async def _refresh(self, season: str) -> dict[str, Any]:
        logger.info("[anime] 开始获取季度番组：%s", season)
        preferences = self.store.get_preferences() if hasattr(self.store, "get_preferences") else {}
        self.bangumi.exclude_r18 = bool(preferences.get("exclude_r18", False))
        results: list[SourceResult] = await asyncio.gather(*(adapter.fetch(season) for adapter in self.adapters))
        records = [record for result in results if result.status == "ok" for record in result.records]
        schedule_source = preferences.get("schedule_source", "earliest")
        items = merge_records(records, schedule_source)
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
        for name, value in status.items():
            if value["status"] == "error":
                logger.error("[anime] 来源 %s 获取失败：%s", name, value["error"] or "未知错误")
            else:
                logger.info("[anime] 来源 %s 获取完成：%s 条", name, value["count"])
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
                current.schedules, current.schedule_note = unify_schedules(current.schedules, schedule_source)
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
            self.store.state["schedule_source_mode"] = schedule_source
            self.store.state["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        self.store.state["source_status"] = status
        self.store.save()
        logger.info("[anime] 季度番组获取完成：%s，合并 %s 部", season, len(items))
        return {"items": items, "sources": status, "updated_at": self.store.state.get("updated_at", "")}

    async def refresh_movies(self, today: date):
        return await self._singleflight(("movies", today), lambda: self._refresh_movies(today))

    async def _refresh_movies(self, today: date):
        preferences = self.store.get_preferences() if hasattr(self.store, "get_preferences") else {}
        self.bangumi.exclude_r18 = bool(preferences.get("exclude_r18", False))
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

    async def _singleflight(
        self,
        key: tuple[str, Hashable],
        operation: Callable[[], Awaitable[Any]],
    ) -> Any:
        task = self._inflight.get(key)
        if task is not None and task.done():
            self._discard_inflight(key, task)
            task = None
        if task is None:
            task = asyncio.create_task(operation())
            self._inflight[key] = task
            task.add_done_callback(lambda completed: self._discard_inflight(key, completed))
        return await asyncio.shield(task)

    def _discard_inflight(self, key: tuple[str, Hashable], task: asyncio.Task[Any]) -> None:
        if self._inflight.get(key) is task:
            del self._inflight[key]
        if not task.cancelled():
            task.exception()

