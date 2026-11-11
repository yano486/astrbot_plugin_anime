from __future__ import annotations


def push_subscription_notice(store, target_id: str) -> str | None:
    """Identify the subscription state before a requested image push."""
    target = store.state.get("targets", {}).get(target_id, {})
    if not target.get("enabled", True) or not target.get("subscribed", False):
        return "push_not_subscribed"
    if not any(sub.enabled for sub in store.get_subscriptions(target_id)):
        return "push_no_anime"
    return None
