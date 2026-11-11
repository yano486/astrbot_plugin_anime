# astrbot_plugin_anime

AstrBot plugin for seasonal Japanese anime schedules, WebUI subscriptions, and reminder delivery.

## Commands

- `/anime help` - English help text.
- `/anime帮助` - Chinese help text.
- `/anime push` / `/anime推送` - Send today's schedule image.
- `/anime week` / `/anime本周` - Send this week's schedule image.
- `/anime ova` / `/anime剧场版` - Send selected movie and OVA release dates.
- `/anime sub` / `/anime订阅` - Enable automatic reminders for the current conversation.
- `/anime绑定`, `/anime解绑`, `/anime列表`, `/anime刷新` - Manage targets and subscriptions.

## WebUI

Open the plugin WebUI to manage targets, schedules, timezones, source preferences, and message templates. Select text or card reminders in Settings. Image messages support three layouts (Info, Poster, Compact) and an independent dark/light palette. These settings apply to command tables, daily/weekly subscription tables, notification cards, and image push tests. Images do not display schedule-source names.

Images render locally with Pillow. Covers are cached for 30 days; unavailable covers use a visible placeholder. Install Noto CJK if the host has no Chinese fonts.

Command replies and reminder text can be edited independently. `/anime help` and `/anime帮助` intentionally use separate templates. Templates support variables such as `{title}`, `{beijing_time}`, `{japan_time}`, `{display_time}`, `{source}`, `{schedule_note}`, `{release_date}`, `{item_type}`, and `{count}`. The WebUI lists the variables valid for each template.

## Layout

See `PROJECT_STRUCTURE.md` for the repository map and module responsibilities.

## License

MIT License. See `LICENSE`.
