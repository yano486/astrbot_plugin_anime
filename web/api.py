from __future__ import annotations

from datetime import date, datetime
from typing import Any

from ..core.models import Subscription
from ..core.time_utils import BJ

SCHEDULE_SOURCES = {"earliest", "yuc", "bgmlist", "bangumi"}
DISPLAY_TIMEZONES = {"Asia/Shanghai", "Asia/Tokyo"}
API_ROUTE_DEFINITIONS = (
    ("status", "status", ("GET",), "Anime plugin status"),
    ("preferences", "preferences", ("GET", "POST"), "Schedule and display preferences"),
    ("items", "items", ("GET",), "Anime catalog"),
    ("targets", "targets", ("GET",), "Bound targets"),
    ("targets/umo", "add_umo_target", ("POST",), "Add AstrBot UMO target"),
    ("targets/whitelist", "update_whitelist", ("POST",), "Update target whitelist"),
    ("subscriptions", "subscriptions", ("GET", "POST"), "Anime subscriptions"),
    ("movie-release", "movie_release", ("POST",), "Set movie release time"),
    ("test-push", "test_push", ("POST",), "Send a test message"),
    ("refresh", "refresh", ("POST",), "Refresh catalog"),
)


def validate_preferences(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("preferences must be an object")
    values = {
        "schedule_source": payload.get("schedule_source", "earliest"),
        "display_timezone": payload.get("display_timezone", "Asia/Shanghai"),
        "exclude_r18": payload.get("exclude_r18", False),
    }
    if not isinstance(values["schedule_source"], str) or values["schedule_source"] not in SCHEDULE_SOURCES:
        raise ValueError("schedule_source must be earliest, yuc, bgmlist, or bangumi")
    if not isinstance(values["display_timezone"], str) or values["display_timezone"] not in DISPLAY_TIMEZONES:
        raise ValueError("display_timezone must be Asia/Shanghai or Asia/Tokyo")
    if not isinstance(values["exclude_r18"], bool):
        raise ValueError("exclude_r18 must be a boolean")
    return values


def validate_umo_target(value: Any) -> tuple[str, str, str]:
    if not isinstance(value, str):
        raise ValueError("UMO must use platform_name:message_type:session_id format")
    parts = value.strip().split(":")
    if (
        len(parts) != 3
        or any(not part or part != part.strip() or any(char.isspace() for char in part) for part in parts)
        or not parts[1].endswith("Message")
    ):
        raise ValueError("UMO must use platform_name:message_type:session_id format")
    return parts[0], parts[1], parts[2]


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
        lead = 0 if is_movie else value.get("lead_minutes", 15)
        enabled = value.get("enabled", True)
        on_time = True if is_movie else value.get("on_time", True)
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
        raise ValueError("release_at must be an ISO local date")
    if "T" in release_at or "t" in release_at:
        raise ValueError("OVA and theatrical release dates must not include a custom time")
    try:
        parsed = date.fromisoformat(release_at)
    except ValueError as exc:
        raise ValueError("release_at must be an ISO local date") from exc
    if len(release_at) != 10:
        raise ValueError("release_at must be an ISO local date")
    return key, parsed.isoformat()


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
        for endpoint, handler_name, methods, description in API_ROUTE_DEFINITIONS:
            context.register_web_api(
                f"{base}/{endpoint}",
                getattr(self, handler_name),
                list(methods),
                description,
            )

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
                    "preferences": self.plugin.store.get_preferences(),
                }
            if endpoint == "preferences":
                if method == "GET":
                    return 200, {"preferences": self.plugin.store.get_preferences()}
                values = validate_preferences(payload)
                self.plugin.store.set_preferences(values)
                self.plugin.store.save()
                return 200, {"preferences": self.plugin.store.get_preferences()}
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
                    if item.key not in movie_keys and season and season != "all" and item.season and item.season != season:
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
            if endpoint == "targets/umo":
                from ..core.models import Target

                platform, message_type, session_id = validate_umo_target((payload or {}).get("umo"))
                target_id = f"{platform}:{message_type}:{session_id}"
                existing = self.plugin.store.state.setdefault("targets", {}).get(target_id)
                if existing is None:
                    self.plugin.store.upsert_target(Target(
                        target_id=target_id,
                        display_name=target_id,
                        platform=platform,
                        enabled=True,
                        updated_at=datetime.now().isoformat(),
                        whitelisted=True,
                    ))
                else:
                    existing["enabled"] = True
                    existing["whitelisted"] = True
                self.plugin.store.save()
                return 200, {"target_id": target_id, "added": existing is None}
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
                    kind = (payload or {}).get("kind", "message")
                    if kind == "message":
                        await self.plugin._deliver(target_id, "🔔 动画订阅测试消息：此会话可以接收插件推送。")
                    elif kind in {"reminder_card", "update_card"}:
                        items = self.plugin.store.get_all_items()
                        key = (payload or {}).get("anime_key")
                        item = next((value for value in items if value.key == key), None) if key else None
                        if kind == "reminder_card" and item is None:
                            item = next((value for value in items if value.item_type in ("tv", "web") and value.schedules), None)
                        if item is None:
                            return 400, {"error": "no suitable anime found; refresh catalog or select an anime"}
                        await self.plugin._deliver_card(target_id, item, "reminder" if kind == "reminder_card" else "update")
                    else:
                        return 400, {"error": "kind must be message, reminder_card, or update_card"}
                except Exception as exc:
                    return 502, {"error": f"test push failed: {exc}"}
                return 200, {"sent": True, "kind": kind}
            if endpoint == "refresh":
                import re

                requested_seasons = (payload or {}).get("seasons")
                season = (payload or {}).get("season") or self.plugin.current_season()
                if requested_seasons is not None:
                    if not isinstance(requested_seasons, list) or not requested_seasons or len(requested_seasons) > 4:
                        return 400, {"error": "seasons must be a list of 1-4 quarter values"}
                    seasons = requested_seasons
                elif isinstance(season, str) and re.fullmatch(r"\d{4}", season):
                    seasons = [f"{season}-{month:02d}" for month in (1, 4, 7, 10)]
                else:
                    seasons = [season]
                if any(not isinstance(value, str) or not re.fullmatch(r"\d{4}-(01|04|07|10)", value) for value in seasons):
                    return 400, {"error": "season values must be YYYY-01, YYYY-04, YYYY-07, or YYYY-10"}
                seasons = list(dict.fromkeys(seasons))
                results = [await self.plugin.refresh_service.refresh(value) for value in seasons]
                movie_result = await self.plugin.refresh_service.refresh_movies(datetime.now(BJ).date()) if hasattr(self.plugin.refresh_service, "refresh_movies") else {"items": [], "sources": {}}
                anime_items = {item.key: item for result in results for item in result["items"]}
                source_status = results[-1]["sources"]
                if len(results) > 1:
                    source_names = {name for result in results for name in result["sources"]}
                    source_status = {
                        name: {
                            **next((result["sources"][name] for result in reversed(results) if name in result["sources"]), {}),
                            "count": sum(result["sources"].get(name, {}).get("count", 0) for result in results),
                            "season_status": {period: result["sources"].get(name, {}).get("status", "error") for period, result in zip(seasons, results)},
                        }
                        for name in source_names
                    }
                return 200, {
                    "count": len(anime_items),
                    "seasons": seasons,
                    "movie_count": len(movie_result["items"]),
                    "sources": source_status,
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
    async def add_umo_target(self): return await self._astrbot("targets/umo")
    async def update_whitelist(self): return await self._astrbot("targets/whitelist")
    async def subscriptions(self): return await self._astrbot("subscriptions")
    async def movie_release(self): return await self._astrbot("movie-release")
    async def test_push(self): return await self._astrbot("test-push")
    async def preferences(self): return await self._astrbot("preferences")
    async def refresh(self): return await self._astrbot("refresh")
