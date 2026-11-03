from __future__ import annotations

import unittest

from astrbot_plugin_anime.web_api import validate_subscriptions


class WebValidationTests(unittest.TestCase):
    def test_rejects_unknown_target(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown target"):
            validate_subscriptions({"target_id": "x", "subscriptions": []}, set(), set())

    def test_rejects_invalid_lead_time(self) -> None:
        payload = {"target_id": "x", "subscriptions": [{"anime_key": "a", "lead_minutes": -1}]}
        with self.assertRaisesRegex(ValueError, "lead_minutes"):
            validate_subscriptions(payload, {"x"}, {"a"})

    def test_creates_subscription_for_only_selected_target(self) -> None:
        payload = {"target_id": "x", "subscriptions": [{"anime_key": "a", "lead_minutes": 30}]}
        values = validate_subscriptions(payload, {"x", "y"}, {"a", "b"})
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0].target_id, "x")
        self.assertEqual(values[0].lead_minutes, 30)

    def test_whitelist_change_requires_an_existing_bound_target(self) -> None:
        from astrbot_plugin_anime.web_api import validate_whitelist_updates

        with self.assertRaisesRegex(ValueError, "unknown target"):
            validate_whitelist_updates({"targets": [{"target_id": "missing", "allowed": True}]}, {"group:1"})

    def test_subscription_activation_is_blocked_for_non_whitelisted_target(self) -> None:
        from astrbot_plugin_anime.web_api import can_activate_target_subscription

        self.assertFalse(can_activate_target_subscription({"enabled": True, "whitelisted": False}))
        self.assertTrue(can_activate_target_subscription({"enabled": True, "whitelisted": True}))

    def test_saving_an_active_subscription_automatically_whitelists_target(self) -> None:
        from astrbot_plugin_anime.web_api import subscription_target_state

        values = validate_subscriptions(
            {"target_id": "x", "subscriptions": [{"anime_key": "a", "enabled": True}]},
            {"x"}, {"a"},
        )
        self.assertEqual(subscription_target_state(values), (True, True))
        disabled = validate_subscriptions(
            {"target_id": "x", "subscriptions": [{"anime_key": "a", "enabled": False}]},
            {"x"}, {"a"},
        )
        self.assertEqual(subscription_target_state(disabled), (False, False))


if __name__ == "__main__":
    unittest.main()
