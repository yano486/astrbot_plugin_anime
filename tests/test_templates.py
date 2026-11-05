from __future__ import annotations

import unittest

from astrbot_plugin_anime.rendering.templates import (
    DEFAULT_MESSAGE_TEMPLATES,
    render_template,
    validate_message_templates,
)


class MessageTemplateTests(unittest.TestCase):
    def test_english_and_chinese_help_have_independent_defaults(self) -> None:
        self.assertIn("/anime help", DEFAULT_MESSAGE_TEMPLATES["help_english"])
        self.assertIn("/anime push", DEFAULT_MESSAGE_TEMPLATES["help_chinese"])

    def test_rendering_substitutes_dynamic_values(self) -> None:
        rendered = render_template(
            "reminder_lead",
            {"title": "测试动画", "beijing_time": "周四 19:30"},
            {"reminder_lead": "{title}\n{beijing_time}"},
        )
        self.assertEqual(rendered, "测试动画\n周四 19:30")

    def test_overriding_one_help_template_does_not_change_the_other(self) -> None:
        overrides = {"help_english": "custom English"}
        self.assertEqual(render_template("help_english", overrides=overrides), "custom English")
        self.assertIn("/anime push", render_template("help_chinese"))

    def test_unknown_variable_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown variable"):
            validate_message_templates({"help_english": "{not_allowed}"})

    def test_malformed_template_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid template"):
            validate_message_templates({"help_chinese": "{title"})

    def test_push_mode_is_validated_by_preferences(self) -> None:
        from astrbot_plugin_anime.web.api import validate_preferences

        self.assertEqual(validate_preferences({"push_mode": "card"})["push_mode"], "card")
        with self.assertRaisesRegex(ValueError, "push_mode"):
            validate_preferences({"push_mode": "image"})


if __name__ == "__main__":
    unittest.main()
