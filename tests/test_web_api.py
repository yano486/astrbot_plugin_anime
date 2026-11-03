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

    def test_movie_subscription_uses_standard_reminder_without_custom_push_time(self) -> None:
        payload = {"target_id": "x", "subscriptions": [{"anime_key": "movie:1", "lead_minutes": 120, "on_time": True}]}
        values = validate_subscriptions(payload, {"x"}, {"movie:1"}, {"movie:1"})
        self.assertEqual(values[0].lead_minutes, 30)
        self.assertFalse(values[0].on_time)

    def test_movie_release_datetime_requires_a_real_catalog_item_and_datetime(self) -> None:
        from astrbot_plugin_anime.web_api import validate_movie_release

        key, release_at = validate_movie_release({"anime_key": "movie:1", "release_at": "2027-04-10T18:30"}, {"movie:1"})
        self.assertEqual((key, release_at), ("movie:1", "2027-04-10T18:30"))
        with self.assertRaisesRegex(ValueError, "unknown anime_key"):
            validate_movie_release({"anime_key": "unknown", "release_at": "2027-04-10T18:30"}, {"movie:1"})
        with self.assertRaisesRegex(ValueError, "release_at"):
            validate_movie_release({"anime_key": "movie:1", "release_at": "bad"}, {"movie:1"})
        self.assertEqual(validate_movie_release({"anime_key": "movie:1", "release_at": ""}, {"movie:1"}), ("movie:1", ""))

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
