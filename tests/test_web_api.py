from __future__ import annotations

import unittest

from astrbot_plugin_anime.web.api import validate_subscriptions


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
        self.assertEqual(values[0].lead_minutes, 0)
        self.assertTrue(values[0].on_time)

    def test_new_tv_subscription_defaults_to_fifteen_minutes(self) -> None:
        values = validate_subscriptions(
            {"target_id": "x", "subscriptions": [{"anime_key": "tv:1"}]},
            {"x"}, {"tv:1"},
        )
        self.assertEqual(values[0].lead_minutes, 15)

    def test_schedule_and_display_preferences_are_validated(self) -> None:
        from astrbot_plugin_anime.web.api import validate_preferences

        self.assertEqual(
            validate_preferences({"schedule_source": "bgmlist", "display_timezone": "Asia/Tokyo"}),
            {"schedule_source": "bgmlist", "display_timezone": "Asia/Tokyo", "exclude_r18": False, "push_mode": "text", "daily_table_enabled": False, "daily_table_time": "00:00", "weekly_table_enabled": False, "weekly_table_time": "00:00", "message_templates": {}},
        )
        with self.assertRaisesRegex(ValueError, "schedule_source"):
            validate_preferences({"schedule_source": "unknown"})
        with self.assertRaisesRegex(ValueError, "display_timezone"):
            validate_preferences({"display_timezone": "UTC"})

    def test_r18_preference_must_be_boolean(self) -> None:
        from astrbot_plugin_anime.web.api import validate_preferences

        self.assertEqual(
            validate_preferences({"exclude_r18": True}),
            {"schedule_source": "earliest", "display_timezone": "Asia/Shanghai", "exclude_r18": True, "push_mode": "text", "daily_table_enabled": False, "daily_table_time": "00:00", "weekly_table_enabled": False, "weekly_table_time": "00:00", "message_templates": {}},
        )
        with self.assertRaisesRegex(ValueError, "exclude_r18"):
            validate_preferences({"exclude_r18": "true"})

    def test_subscription_table_preferences_default_to_disabled_midnight(self) -> None:
        from astrbot_plugin_anime.web.api import validate_preferences

        values = validate_preferences({})
        self.assertFalse(values["daily_table_enabled"])
        self.assertEqual(values["daily_table_time"], "00:00")
        self.assertFalse(values["weekly_table_enabled"])
        self.assertEqual(values["weekly_table_time"], "00:00")

    def test_subscription_table_preferences_validate_switches_and_times(self) -> None:
        from astrbot_plugin_anime.web.api import validate_preferences

        values = validate_preferences({
            "daily_table_enabled": True,
            "daily_table_time": "08:30",
            "weekly_table_enabled": True,
            "weekly_table_time": "23:59",
        })
        self.assertTrue(values["daily_table_enabled"])
        self.assertEqual(values["daily_table_time"], "08:30")
        self.assertTrue(values["weekly_table_enabled"])
        self.assertEqual(values["weekly_table_time"], "23:59")
        with self.assertRaisesRegex(ValueError, "daily_table_time"):
            validate_preferences({"daily_table_time": "24:00"})
        with self.assertRaisesRegex(ValueError, "weekly_table_enabled"):
            validate_preferences({"weekly_table_enabled": "true"})

    def test_umo_target_requires_astrbot_three_part_format(self) -> None:
        from astrbot_plugin_anime.web.api import validate_umo_target

        self.assertEqual(validate_umo_target("default:FriendMessage:123456789"), ("default", "FriendMessage", "123456789"))
        self.assertEqual(validate_umo_target("bot:GroupMessage:group-42"), ("bot", "GroupMessage", "group-42"))
        with self.assertRaisesRegex(ValueError, "UMO"):
            validate_umo_target("default:123456789")

    def test_movie_release_date_requires_a_real_catalog_item(self) -> None:
        from astrbot_plugin_anime.web.api import validate_movie_release

        key, release_at = validate_movie_release({"anime_key": "movie:1", "release_at": "2027-04-10"}, {"movie:1"})
        self.assertEqual((key, release_at), ("movie:1", "2027-04-10"))
        with self.assertRaisesRegex(ValueError, "unknown anime_key"):
            validate_movie_release({"anime_key": "unknown", "release_at": "2027-04-10"}, {"movie:1"})
        with self.assertRaisesRegex(ValueError, "release_at"):
            validate_movie_release({"anime_key": "movie:1", "release_at": "bad"}, {"movie:1"})
        with self.assertRaisesRegex(ValueError, "custom time"):
            validate_movie_release({"anime_key": "movie:1", "release_at": "2027-04-10T18:30"}, {"movie:1"})
        self.assertEqual(validate_movie_release({"anime_key": "movie:1", "release_at": ""}, {"movie:1"}), ("movie:1", ""))

    def test_whitelist_change_requires_an_existing_bound_target(self) -> None:
        from astrbot_plugin_anime.web.api import validate_whitelist_updates

        with self.assertRaisesRegex(ValueError, "unknown target"):
            validate_whitelist_updates({"targets": [{"target_id": "missing", "allowed": True}]}, {"group:1"})

    def test_subscription_activation_is_blocked_for_non_whitelisted_target(self) -> None:
        from astrbot_plugin_anime.web.api import can_activate_target_subscription

        self.assertFalse(can_activate_target_subscription({"enabled": True, "whitelisted": False}))
        self.assertTrue(can_activate_target_subscription({"enabled": True, "whitelisted": True}))

    def test_saving_an_active_subscription_automatically_whitelists_target(self) -> None:
        from astrbot_plugin_anime.web.api import subscription_target_state

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
