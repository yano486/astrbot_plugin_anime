from __future__ import annotations

from datetime import datetime
from typing import Any

from .models import Subscription


def validate_subscriptions(
    payload: Any,
    target_ids: set[str],
    item_keys: set[str],
    movie_keys: set[str] | None = None,
) -> list[Subscription]:
    if not isinstance(payload, dict) or not isinstance(payload.get("target_id"), str):
        raise ValueError("target_id is required")
    target_id = payload["target_id"]
    if target_id not in target_ids:
        raise ValueError("unknown target")
    values = payload.get("subscriptions")
    if not isinstance(values, list) or len(values) > 500:
        raise ValueError("subscriptions must be a list of at most 500 items")
    result = []
    seen = set()
    for value in values:
        if not isinstance(value, dict):
            raise ValueError("subscription entry must be an object")
        key = value.get("anime_key")
        if not isinstance(key, str):
            raise ValueError("anime_key must be a string")
        is_movie = key in (movie_keys or set())
        lead = 30 if is_movie else value.get("lead_minutes", 0)
        enabled = value.get("enabled", True)
        on_time = False if is_movie else value.get("on_time", True)
        if key not in item_keys:
            raise ValueError("unknown anime_key")
        if not is_movie and (isinstance(lead, bool) or not isinstance(lead, int) or not 0 <= lead <= 1440):
            raise ValueError("lead_minutes must be an integer from 0 to 1440")
        if not isinstance(enabled, bool) or not isinstance(on_time, bool):
            raise ValueError("enabled and on_time must be booleans")
        if key in seen:
            continue
        seen.add(key)
        result.append(Subscription(target_id, key, enabled, lead, on_time))
    return result


def validate_movie_release(payload: Any, movie_keys: set[str]) -> tuple[str, str]:
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    key, release_at = payload.get("anime_key"), payload.get("release_at")
    if not isinstance(key, str) or key not in movie_keys:
        raise ValueError("unknown anime_key")
    if release_at == "":
        return key, ""
    if not isinstance(release_at, str):
        raise ValueError("release_at must be an ISO local date and time")
    try:
        parsed = datetime.fromisoformat(release_at)
    except ValueError as exc:
        raise ValueError("release_at must be an ISO local date and time") from exc
    if parsed.tzinfo is not None or "T" not in release_at:
        raise ValueError("release_at must be an ISO local date and time")
    return key, parsed.replace(second=0, microsecond=0).isoformat(timespec="minutes")


def validate_whitelist(payload: Any, target_ids: set[str]) -> tuple[str, bool]:
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    target_id, allowed = payload.get("target_id"), payload.get("allowed")
    if target_id not in target_ids:
        raise ValueError("unknown target")
    if not isinstance(allowed, bool):
        raise ValueError("allowed must be a boolean")
    return target_id, allowed


def validate_whitelist_updates(payload: Any, target_ids: set[str]) -> list[tuple[str, bool]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("targets"), list):
        raise ValueError("targets must be a list")
    result = []
    seen = set()
    for value in payload["targets"]:
        target_id, allowed = validate_whitelist(value, target_ids)
        if target_id not in seen:
            seen.add(target_id)
            result.append((target_id, allowed))
    return result


def can_activate_target_subscription(target: dict[str, Any]) -> bool:
    return bool(target.get("enabled", True) and target.get("whitelisted", False))


def subscription_target_state(subscriptions: list[Subscription]) -> tuple[bool, bool]:
    active = any(subscription.enabled for subscription in subscriptions)
    return active, active


class AnimeWebAPI:
    def __init__(self, plugin: Any):
        self.plugin = plugin

    def register(self) -> None:
        context = self.plugin.context
        base = "/astrbot_plugin_anime"
        routes = [
            ("/status", self.status, ["GET"], "Anime plugin status"),
            ("/items", self.items, ["GET"], "Anime catalog"),
            ("/targets", self.targets, ["GET"], "Bound targets"),
            ("/targets/whitelist", self.update_whitelist, ["POST"], "Update target whitelist"),
            ("/subscriptions", self.subscriptions, ["GET", "POST"], "Anime subscriptions"),
            ("/movie-release", self.movie_release, ["POST"], "Set movie release time"),
            ("/test-push", self.test_push, ["POST"], "Send a test message"),
            ("/refresh", self.refresh, ["POST"], "Refresh catalog"),
        ]
        for suffix, handler, methods, desc in routes:
            context.register_web_api(base + suffix, handler, methods, desc)

    async def execute(self, endpoint: str, method: str, query: Any, payload: Any = None) -> tuple[int, dict[str, Any]]:
        try:
            if endpoint == "status":
                return 200, {
                    "season": self.plugin.current_season(),
                    "updated_at": self.plugin.store.state.get("updated_at", ""),
                    "movie_catalog_updated_at": self.plugin.store.state.get("movie_catalog_updated_at", ""),
                    "sources": self.plugin.store.state.get("source_status", {}),
                    "movie_sources": self.plugin.store.state.get("movie_source_status", {}),
                    "remote_webui_url": self.plugin.remote_webui_url,
                    "remote_webui_enabled": self.plugin.remote_webui_enabled,
                    "remote_webui_password_enabled": bool(getattr(self.plugin, "remote_webui_password_enabled", False)),
                }
            if endpoint == "items":
                season = query.get("season", self.plugin.current_season())
                query_text = str(query.get("q", "")).strip().casefold()
                region, item_type = str(query.get("region", "")), str(query.get("type", ""))
                weekday_text = query.get("weekday", "")
                weekday = int(weekday_text) if str(weekday_text).isdigit() else None
                source = str(query.get("source", ""))
                items = []
                movie_keys = {item.key for item in self.plugin.store.get_movie_items()}
                for item in self.plugin.store.get_all_items():
                    if item.key not in movie_keys and season and item.season and item.season != season:
                        continue
                    if query_text and query_text not in (item.title + " " + item.title_cn + " " + " ".join(item.aliases)).casefold():
                        continue
                    if region == "jp" and item.region != "jp":
                        continue
                    if region == "unknown" and item.region not in ("unknown", "mixed"):
                        continue
                    if item_type and item_type != item.item_type:
                        continue
                    if source and source not in item.sources:
                        continue
                    if weekday and not any(schedule.weekday == weekday for schedule in item.schedules):
                        continue
                    value = item.to_dict()
                    if item.key in movie_keys:
                        value["release_at"] = self.plugin.store.get_movie_release_override(item.key)
                    items.append(value)
                return 200, {
                    "items": items,
                    "count": len(items),
                    "updated_at": self.plugin.store.state.get("updated_at", ""),
                    "movie_catalog_updated_at": self.plugin.store.state.get("movie_catalog_updated_at", ""),
                }
            if endpoint == "targets":
                return 200, {"targets": [target.__dict__ for target in self.plugin.store.get_targets()]}
            if endpoint == "targets/whitelist":
                changes = validate_whitelist_updates(
                    payload,
                    {target.target_id for target in self.plugin.store.get_targets()},
                )
                for target_id, allowed in changes:
                    target = self.plugin.store.state["targets"][target_id]
                    target["whitelisted"] = allowed
                    if not allowed:
                        target["subscribed"] = False
                self.plugin.store.save()
                return 200, {"updated": len(changes)}
            if endpoint == "subscriptions":
                target_id = query.get("target_id")
                if method == "GET":
                    values = [sub.__dict__ for sub in self.plugin.store.get_subscriptions(target_id)] if target_id else []
                    return 200, {"subscriptions": values}
                movie_keys = {item.key for item in self.plugin.store.get_movie_items()}
                valid = validate_subscriptions(
                    payload,
                    {target.target_id for target in self.plugin.store.get_targets()},
                    {item.key for item in self.plugin.store.get_all_items()},
                    movie_keys,
                )
                target_id = payload["target_id"]
                for key in list(self.plugin.store.state.get("subscriptions", {})):
                    if key.startswith(target_id + "\0"):
                        del self.plugin.store.state["subscriptions"][key]
                for sub in valid:
                    self.plugin.store.set_subscription(sub)
                target_state = self.plugin.store.state.setdefault("targets", {}).get(target_id)
                if target_state is not None:
                    whitelisted, subscribed = subscription_target_state(valid)
                    target_state["subscribed"] = subscribed
                    target_state["whitelisted"] = whitelisted
                self.plugin.store.save()
                return 200, {"saved": len(valid)}
            if endpoint == "movie-release":
                movie_keys = {item.key for item in self.plugin.store.get_movie_items()}
                key, release_at = validate_movie_release(payload, movie_keys)
                if release_at:
                    self.plugin.store.set_movie_release_override(key, release_at)
                else:
                    self.plugin.store.clear_movie_release_override(key)
                self.plugin.store.save()
                return 200, {"saved": True, "anime_key": key, "release_at": release_at}
            if endpoint == "test-push":
                target_id = payload.get("target_id") if isinstance(payload, dict) else None
                target = self.plugin.store.state.get("targets", {}).get(target_id)
                if not target or not target.get("enabled", True):
                    return 400, {"error": "unknown or disabled target"}
                try:
                    await self.plugin._deliver(target_id, "🔔 动画订阅测试消息：此会话可以接收插件推送。")
                except Exception as exc:
                    return 502, {"error": f"test push failed: {exc}"}
                return 200, {"sent": True}
            if endpoint == "refresh":
                import re

                season = (payload or {}).get("season") or self.plugin.current_season()
                if not isinstance(season, str) or not re.fullmatch(r"\d{4}-(01|04|07|10)", season):
                    return 400, {"error": "season must be YYYY-01, YYYY-04, YYYY-07, or YYYY-10"}
                result = await self.plugin.refresh_service.refresh(season)
                movie_result = await self.plugin.refresh_service.refresh_movies(datetime.now(BJ).date())
                return 200, {
                    "count": len(result["items"]),
                    "movie_count": len(movie_result["items"]),
                    "sources": result["sources"],
                    "movie_sources": {name: {"status": value.status, "error": value.error, "source_url": value.source_url} for name, value in movie_result["sources"].items()},
                }
            return 404, {"error": "not found"}
        except ValueError as exc:
            return 400, {"error": str(exc)}
        except Exception as exc:
            return 502, {"error": f"{endpoint} failed: {exc}"}

    async def _astrbot(self, endpoint: str):
        from astrbot.api.web import error_response, json_response, request

        payload = await request.json(default={}) if request.method != "GET" else None
        status, value = await self.execute(endpoint, request.method, request.query, payload)
        if status >= 400:
            return error_response(value.get("error", "request failed"), status_code=status)
        return json_response(value)

    async def status(self): return await self._astrbot("status")
    async def items(self): return await self._astrbot("items")
    async def targets(self): return await self._astrbot("targets")
    async def update_whitelist(self): return await self._astrbot("targets/whitelist")
    async def subscriptions(self): return await self._astrbot("subscriptions")
    async def movie_release(self): return await self._astrbot("movie-release")
    async def test_push(self): return await self._astrbot("test-push")
    async def refresh(self): return await self._astrbot("refresh")
