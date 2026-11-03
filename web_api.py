from __future__ import annotations

from typing import Any

from .models import Subscription


def validate_subscriptions(payload: Any, target_ids: set[str], item_keys: set[str]) -> list[Subscription]:
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
        lead = value.get("lead_minutes", 0)
        enabled = value.get("enabled", True)
        on_time = value.get("on_time", True)
        if key not in item_keys:
            raise ValueError("unknown anime_key")
        if isinstance(lead, bool) or not isinstance(lead, int) or not 0 <= lead <= 1440:
            raise ValueError("lead_minutes must be an integer from 0 to 1440")
        if not isinstance(enabled, bool) or not isinstance(on_time, bool):
            raise ValueError("enabled and on_time must be booleans")
        if key in seen:
            continue
        seen.add(key)
        result.append(Subscription(target_id, key, enabled, lead, on_time))
    return result


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
            ("/refresh", self.refresh, ["POST"], "Refresh catalog"),
        ]
        for suffix, handler, methods, desc in routes:
            context.register_web_api(base + suffix, handler, methods, desc)

    async def status(self):
        from astrbot.api.web import json_response

        return json_response({
            "season": self.plugin.current_season(),
            "updated_at": self.plugin.store.state.get("updated_at", ""),
            "sources": self.plugin.store.state.get("source_status", {}),
        })

    async def items(self):
        from astrbot.api.web import json_response, request

        season = request.query.get("season", self.plugin.current_season())
        query = str(request.query.get("q", "")).strip().casefold()
        region = str(request.query.get("region", ""))
        item_type = str(request.query.get("type", ""))
        weekday = request.query.get("weekday", type=int)
        source = str(request.query.get("source", ""))
        items = []
        for item in self.plugin.store.get_items():
            if season and item.season and item.season != season:
                continue
            if query and query not in (item.title + " " + item.title_cn + " " + " ".join(item.aliases)).casefold():
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
            items.append(item.to_dict())
        return json_response({"items": items, "count": len(items)})

    async def targets(self):
        from astrbot.api.web import json_response

        return json_response({"targets": [target.__dict__ for target in self.plugin.store.get_targets()]})

    async def update_whitelist(self):
        from astrbot.api.web import error_response, json_response, request

        payload = await request.json(default={})
        try:
            changes = validate_whitelist_updates(
                payload,
                {target.target_id for target in self.plugin.store.get_targets()},
            )
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        for target_id, allowed in changes:
            target = self.plugin.store.state["targets"][target_id]
            target["whitelisted"] = allowed
            if not allowed:
                target["subscribed"] = False
        self.plugin.store.save()
        return json_response({"updated": len(changes)})

    async def subscriptions(self):
        from astrbot.api.web import error_response, json_response, request

        target_id = request.query.get("target_id")
        if request.method == "GET":
            if not target_id:
                return json_response({"subscriptions": []})
            values = [sub.__dict__ for sub in self.plugin.store.get_subscriptions(target_id)]
            return json_response({"subscriptions": values})
        payload = await request.json(default={})
        try:
            valid = validate_subscriptions(
                payload,
                {target.target_id for target in self.plugin.store.get_targets()},
                {item.key for item in self.plugin.store.get_items()},
            )
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        target = payload["target_id"]
        for key in list(self.plugin.store.state.get("subscriptions", {})):
            if key.startswith(target + "\0"):
                del self.plugin.store.state["subscriptions"][key]
        for sub in valid:
            self.plugin.store.set_subscription(sub)
        target_state = self.plugin.store.state.setdefault("targets", {}).get(target)
        if target_state is not None:
            whitelisted, subscribed = subscription_target_state(valid)
            target_state["subscribed"] = subscribed
            target_state["whitelisted"] = whitelisted
        self.plugin.store.save()
        return json_response({"saved": len(valid)})

    async def refresh(self):
        import re
        from astrbot.api.web import error_response, json_response, request

        try:
            payload = await request.json(default={}) if request.method == "POST" else {}
            season = payload.get("season") or self.plugin.current_season()
            if not isinstance(season, str) or not re.fullmatch(r"\d{4}-(01|04|07|10)", season):
                return error_response("season must be YYYY-01, YYYY-04, YYYY-07, or YYYY-10", status_code=400)
            result = await self.plugin.refresh_service.refresh(season)
        except Exception as exc:
            return error_response(f"refresh failed: {exc}", status_code=502)
        return json_response({"count": len(result["items"]), "sources": result["sources"]})
