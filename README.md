# astrbot_plugin_anime

AstrBot plugin for seasonal Japanese anime schedules, WebUI subscriptions, and reminder delivery.

## Commands

- `/anime help` - English help text.
- `/anime帮助` - Chinese help text.
- `/anime push` / `/anime推送` - Send today's schedule for this conversation's enabled anime subscriptions.
- `/anime week` / `/anime本周` - Send this week's schedule for this conversation's enabled anime subscriptions.
- `/anime ova` / `/anime剧场版` - Send selected movie and OVA release dates.
- `/anime sub` / `/anime订阅` - Enable automatic reminders for the current conversation.
- `/anime绑定`, `/anime解绑`, `/anime列表`, `/anime刷新` - Manage targets and subscriptions.

## WebUI

Open the plugin WebUI to manage targets, schedules, timezones, source preferences, and message templates. Select text or card reminders in Settings. Single-anime cards support three layouts (Info, Poster, Compact). Daily/weekly tables use weekday swimlanes with wrapping cover cards. All images use an independent dark/light palette and do not display schedule-source names.

Image pushes and card-test choices use only the selected conversation's saved, enabled subscriptions. Inactive targets receive a subscription notice; active targets without selected anime receive an empty-selection notice. The full catalog remains available for choosing new subscriptions. Both notices can be edited in Message Text.

Images render locally with Pillow. Covers are cached for 30 days; unavailable covers use a visible placeholder. Install Noto CJK if the host has no Chinese fonts.

Command replies and reminder text can be edited independently. `/anime help` and `/anime帮助` intentionally use separate templates. Templates support variables such as `{title}`, `{beijing_time}`, `{japan_time}`, `{display_time}`, `{source}`, `{schedule_note}`, `{release_date}`, `{item_type}`, and `{count}`. The WebUI lists the variables valid for each template.

## Layout

See `PROJECT_STRUCTURE.md` for the repository map and module responsibilities.

## License

MIT License. See `LICENSE`.
