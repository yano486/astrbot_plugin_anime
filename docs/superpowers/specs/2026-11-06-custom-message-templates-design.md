# Custom Message Templates Design

## Goal

Allow every user-visible plugin reply and text notification to be edited from the WebUI, while preserving the current default wording and keeping message variables available for dynamic anime data.

## Confirmed Decisions

- Display author as `486` in plugin metadata and repository documentation.
- `/anime help` and `/anime帮助` are separate message templates and can be edited independently.
- All command replies are configurable, not only automatic reminder messages.
- Text and card are mutually exclusive push modes in WebUI. Text mode is implemented first; the existing card channel remains available without redesigning card layouts in this change.
- Default templates must reproduce the current behavior unless the user changes them.
- Plugin version advances from `0.2.14` to `0.3.0` for this feature release.
- Add a root-level `LICENSE` using MIT License and a root-level `PROJECT_STRUCTURE.md` explaining the repository for future maintainers.

## Template Groups

The settings store will contain named templates for these groups:

### Command Replies

- `help_english`: `/anime help`
- `help_chinese`: `/anime帮助`
- `bind_success`, `bind_failure`
- `unbind_success`, `unbind_failure`
- `subscription_status`, `subscription_disabled`
- `list_empty`, `list_result`
- `refresh_result`
- `command_usage`
- `unknown_session`
- `no_movie_selection`
- `no_subscription`

### Text Notifications

- `reminder_lead`: automatic notification before a TV/WEB broadcast
- `reminder_on_time`: automatic notification at broadcast time
- `movie_reminder`: OVA/movie date notification

The existing test-message and test-card actions keep their current operational path; their visible text is also routed through named templates where a text body exists.

## Variables

Templates use Python-style `{variable}` placeholders. The renderer validates variables against the template group before saving and rejects unknown names or malformed braces.

Common variables:

- `{title}`: preferred Chinese title, otherwise the source title
- `{item_type}`: TV, WEB, OVA, or movie label
- `{reminder_label}`: current reminder wording
- `{beijing_time}`: formatted Beijing weekday and time
- `{japan_time}`: formatted Japan weekday and time
- `{display_time}`: time in the configured display timezone
- `{source}`: merged source names
- `{schedule_note}`: source-time explanation, including the non-live-confirmation note
- `{weekday}`: configured display weekday
- `{raw_time}`: original source clock when available
- `{lead_minutes}`: configured advance minutes
- `{release_date}`: movie/OVA release date
- `{release_timezone}`: timezone used for the release date
- `{target}`: current conversation target name when available
- `{count}`: result count for command replies that report a count
- `{failed_sources}`: failed source names for refresh replies
- `{subscriptions}`: rendered subscription lines for list replies

Each WebUI template editor displays only the variables valid for that template. Missing optional values resolve to an empty string or the existing user-facing fallback, while unknown variables remain a validation error.

## Data and API

- Extend the stored WebUI preferences with `push_mode` (`text` or `card`) and a `message_templates` mapping.
- Migrate existing state by filling missing templates from defaults; never overwrite user-defined values.
- Extend `validate_preferences()` to validate the mode and every supplied template key, type, length, and variable set.
- Keep the existing `/preferences` GET/POST endpoint; return the normalized mode and templates through it so embedded and remote WebUI use the same API.
- Add a template metadata endpoint or include template definitions in the preferences response so the WebUI can render labels, defaults, and allowed variables without duplicating the variable registry.

## Rendering Flow

- Introduce one template renderer that receives a template key and a context mapping.
- `format_reminder()` and `format_movie_reminder()` build their existing dynamic context and render the configured template instead of concatenating fixed strings.
- Command handlers call the same renderer for their named reply keys; command-specific values such as counts and subscription lines are supplied by the handler.
- Default fallback behavior remains inside the renderer so a missing legacy preference does not produce an empty response.
- Card rendering is not redesigned now; the push-mode field is stored and exposed for the next card-template phase.

## WebUI

- Add a “推送方式” selector with `文字` and `卡片` options.
- Add a “消息文本” section with grouped editors for command replies and notifications.
- Show each template's label, short explanation, allowed variables, editable textarea, restore-default action, and save status.
- Keep the existing schedule, timezone, R18, whitelist, and test-push settings unchanged.
- Use the existing custom controls and theme system; do not introduce native browser dialogs or uncontrolled inputs.

## Metadata and Documentation

- Update `metadata.yaml` author to `486`, description, command descriptions, repository information, and version `0.3.0`.
- Update `main.py` registration author/version and command decorators or command metadata so AstrBot's plugin page lists accurate command descriptions rather than “无描述”.
- Add `LICENSE` with MIT text and copyright holder `486`.
- Add `PROJECT_STRUCTURE.md` at repository root with a plain-language tree and the purpose of each directory/file.
- Update `README.md` with installation, command list, WebUI template configuration, supported variables, and license information.

## Validation

- Add unit tests for default template migration, independent Chinese/English help templates, variable rendering, malformed/unknown variable rejection, and text/card preference validation.
- Add command tests proving `/anime help` and `/anime帮助` use different configured templates.
- Add WebUI tests for template controls, save/load behavior, mode selection, and default restoration.
- Run the full Python suite, both WebUI Node test files, and Python compilation checks.
- Inspect the final diff for secrets, accidental language changes, stale command names, and version mismatch before publishing.
