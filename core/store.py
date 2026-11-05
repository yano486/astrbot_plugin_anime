from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .models import AnimeItem, Subscription, Target
from ..rendering.templates import DEFAULT_MESSAGE_TEMPLATES


DEFAULT_PREFERENCES = {
    "schedule_source": "earliest",
    "display_timezone": "Asia/Shanghai",
    "exclude_r18": False,
    "push_mode": "text",
    "message_templates": dict(DEFAULT_MESSAGE_TEMPLATES),
}


class JsonStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.state: dict[str, Any] = {
            "items": [],
            "movie_items": [],
            "targets": {},
            "subscriptions": {},
            "movie_release_overrides": {},
            "receipts": [],
            "source_status": {},
            "preferences": dict(DEFAULT_PREFERENCES),
            "updated_at": "",
        }
        self.load()

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self.state
        loaded = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("anime_state.json must contain an object; existing file was not modified")
        self.state.update(loaded)
        return self.state

    def save(self, state: dict[str, Any] | None = None) -> None:
        if state is not None:
            self.state = state
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, self.path)

    def get_items(self) -> list[AnimeItem]:
        return [AnimeItem.from_dict(item) for item in self.state.get("items", [])]

    def set_items(self, items: list[AnimeItem], source_status: dict[str, Any] | None = None) -> None:
        self.state["items"] = [item.to_dict() for item in items]
        if source_status is not None:
            self.state["source_status"] = source_status

    def get_movie_items(self) -> list[AnimeItem]:
        return [AnimeItem.from_dict(item) for item in self.state.get("movie_items", [])]

    def set_movie_items(self, items: list[AnimeItem]) -> None:
        self.state["movie_items"] = [item.to_dict() for item in items]

    def get_all_items(self) -> list[AnimeItem]:
        by_key = {item.key: item for item in self.get_items()}
        by_key.update({item.key: item for item in self.get_movie_items()})
        return list(by_key.values())

    def set_movie_release_override(self, item_key: str, release_at: str) -> None:
        self.state.setdefault("movie_release_overrides", {})[item_key] = release_at

    def clear_movie_release_override(self, item_key: str) -> None:
        self.state.setdefault("movie_release_overrides", {}).pop(item_key, None)

    def get_movie_release_override(self, item_key: str) -> str:
        return str(self.state.get("movie_release_overrides", {}).get(item_key, ""))

    def get_preferences(self) -> dict[str, str]:
        saved = self.state.get("preferences", {})
        templates = {**DEFAULT_MESSAGE_TEMPLATES, **saved.get("message_templates", {})}
        return {**DEFAULT_PREFERENCES, **saved, "message_templates": templates}

    def set_preferences(self, values: dict[str, str]) -> None:
        self.state["preferences"] = {**self.get_preferences(), **values}

    def get_targets(self) -> list[Target]:
        return [Target(**value) for value in self.state.get("targets", {}).values()]

    def upsert_target(self, target: Target) -> None:
        self.state.setdefault("targets", {})[target.target_id] = target.__dict__

    def remove_target(self, target_id: str) -> None:
        self.state.setdefault("targets", {}).pop(target_id, None)
        for key in list(self.state.setdefault("subscriptions", {})):
            if key.startswith(target_id + "\0"):
                del self.state["subscriptions"][key]

    def get_subscriptions(self, target_id: str | None = None) -> list[Subscription]:
        values = []
        for value in self.state.get("subscriptions", {}).values():
            if target_id is None or value["target_id"] == target_id:
                values.append(Subscription(**value))
        return values

    def set_subscription(self, subscription: Subscription) -> None:
        key = subscription.target_id + "\0" + subscription.anime_key
        self.state.setdefault("subscriptions", {})[key] = subscription.__dict__

    def has_receipt(self, key: str) -> bool:
        return key in self.state.setdefault("receipts", [])

    def add_receipt(self, key: str) -> None:
        receipts = self.state.setdefault("receipts", [])
        if key not in receipts:
            receipts.append(key)
            self.state["receipts"] = receipts[-2000:]
