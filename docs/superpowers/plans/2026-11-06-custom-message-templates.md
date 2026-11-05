# Custom Message Templates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add editable command and notification text templates with validated variables, expose them in WebUI, update plugin metadata/docs, and preserve the current default behavior.

**Architecture:** Keep a single template registry in `rendering/templates.py` containing defaults, labels, allowed variables, and rendering validation. Store only user overrides plus the text/card mode in `JsonStore`; merge defaults at read time so old state files migrate without destructive rewrites. Route command replies and reminder formatting through the same renderer, while leaving card image layout unchanged.

**Tech Stack:** Python 3.10+, unittest, Node.js test runner, existing AstrBot WebUI bridge and custom controls.

**Spec:** `docs/superpowers/specs/2026-11-06-custom-message-templates-design.md`

## Global Constraints

- Display author as `486` in plugin metadata and repository documentation.
- `/anime help` and `/anime帮助` remain separate editable templates.
- Preserve current default wording and existing card rendering behavior.
- Use Python-style `{variable}` placeholders and reject unknown or malformed variables.
- Store `push_mode` as `text` or `card`; default to `text`.
- Bump plugin version from `0.2.14` to `0.3.0` in both `main.py` and `metadata.yaml`.
- Add root `LICENSE` with MIT License and root `PROJECT_STRUCTURE.md`.
- Do not include credentials or private server data in source, tests, or documentation.

---

### Task 1: Add the template registry and preference migration

**Files:**
- Create: `rendering/templates.py`
- Modify: `core/store.py`, `web/api.py`
- Test: `tests/test_templates.py`, `tests/test_store.py`, `tests/test_web_api.py`

**Interfaces:**
- Produces `DEFAULT_MESSAGE_TEMPLATES`, `TEMPLATE_DEFINITIONS`, `template_context()`, `render_template(key, values, overrides=None)`, and `validate_message_templates(value)`.
- `JsonStore.get_preferences()` returns `push_mode` and merged `message_templates` without rewriting old state until an ordinary save occurs.
- `validate_preferences()` accepts and returns `push_mode` and `message_templates`.

- [ ] **Step 1: Write failing tests for defaults and independent help templates**

Add tests asserting the default `help_english` contains `/anime help`, the default `help_chinese` contains `/anime帮助`, changing one override does not change the other, and rendering `{title}` plus `{beijing_time}` substitutes values.

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `$env:PYTHONPATH='..'; python -m unittest discover -s tests -p 'test_templates.py' -v`
Expected: import or missing-registry failures because the template module does not exist.

- [ ] **Step 3: Implement the registry and safe renderer**

Define each command/reply key from the spec with its default text, Chinese label, description, and allowed variables. Parse placeholders with `string.Formatter`, reject malformed braces, unknown names, non-string values, and templates longer than 4000 characters. Render missing values as empty strings through a mapping that preserves existing fallback strings.

- [ ] **Step 4: Add preference migration and validation**

Extend `DEFAULT_PREFERENCES` with `push_mode: "text"` and a copy of the default template mapping. Ensure `get_preferences()` overlays saved overrides onto defaults. Extend `validate_preferences()` with `push_mode` and the template validator while preserving the old schedule, timezone, and R18 defaults.

- [ ] **Step 5: Run focused tests and refactor only after green**

Run: `$env:PYTHONPATH='..'; python -m unittest discover -s tests -p 'test_templates.py' -v; python -m unittest discover -s tests -p 'test_store.py' -v; python -m unittest discover -s tests -p 'test_web_api.py' -v`
Expected: all focused tests pass.

### Task 2: Route command replies and notifications through templates

**Files:**
- Modify: `rendering/formatters.py`, `services/scheduler.py`, `main.py`
- Test: `tests/test_commands.py`, `tests/test_scheduler.py`, `tests/test_push_tables.py`

**Interfaces:**
- `format_reminder()` and `format_movie_reminder()` accept optional template overrides and render `reminder_lead`, `reminder_on_time`, and `movie_reminder`.
- `AnimePlugin._reply(event, key, values)` renders a named command template and returns `event.plain_result(...)`.
- `_action_name()` recognizes `help` and `帮助` as distinct help actions where the Chinese standalone command remains handled by `help()`.

- [ ] **Step 1: Write failing tests for command-specific help templates**

Add tests that create a minimal plugin/store with different `help_english` and `help_chinese` overrides, invoke `/anime help` through `anime_command` and `anime帮助` through `help`, and assert each response uses its own text. Add a scheduler test proving a customized `reminder_lead` appears in the delivered message.

- [ ] **Step 2: Run focused tests and verify the new assertions fail**

Run: `$env:PYTHONPATH='..'; python -m unittest discover -s tests -p 'test_commands.py' -v; python -m unittest discover -s tests -p 'test_scheduler.py' -v`
Expected: the existing hard-coded help/reminder text is returned instead of the configured override.

- [ ] **Step 3: Add formatter context and template rendering**

Build the context from the current item, schedule, timezone labels, source list, schedule note, release date, and lead minutes. Pass `store.get_preferences().get("message_templates")` from the scheduler into the formatter. Keep the existing default output byte-for-byte equivalent where practical.

- [ ] **Step 4: Replace hard-coded command responses**

Add a small `_reply()` helper in `main.py`. Replace help, bind, unbind, subscription, list, refresh, missing-target, missing-selection, and usage responses with named template keys and explicit context values. Keep dynamic list lines and failure-source text as variables instead of concatenating fixed prose outside the renderer.

- [ ] **Step 5: Run focused tests and refactor after green**

Run: `$env:PYTHONPATH='..'; python -m unittest discover -s tests -p 'test_commands.py' -v; python -m unittest discover -s tests -p 'test_scheduler.py' -v; python -m unittest discover -s tests -p 'test_push_tables.py' -v`
Expected: all focused tests pass and card/image tests remain unchanged.

### Task 3: Expose mode and message editors in WebUI

**Files:**
- Modify: `web/api.py`, `views/management/index.html`, `views/management/app.js`, `views/management/style.css`
- Test: `tests/test_management.mjs`, `tests/test_web_api_integration.py`

**Interfaces:**
- Preferences GET includes `push_mode`, `message_templates`, and `template_definitions`.
- Preferences POST accepts the same normalized payload.
- WebUI renders one editor per template definition and saves all values through the existing `/preferences` endpoint.

- [ ] **Step 1: Add failing WebUI and API tests**

Assert the settings markup contains the push-mode selector, message-template panel, template keys for both help variants, variable hints, save/reset controls, and that the API returns independent templates and rejects an invalid mode or unknown placeholder.

- [ ] **Step 2: Run focused tests and verify they fail**

Run: `node --test tests/test_management.mjs; $env:PYTHONPATH='..'; python -m unittest discover -s tests -p 'test_web_api_integration.py' -v`
Expected: missing selectors/metadata and validation failures.

- [ ] **Step 3: Return template metadata from the preferences API**

Include stable definitions with `key`, `label`, `description`, `default`, and `variables`; do not expose private values or server paths. Keep POST response normalized and merge missing keys from defaults.

- [ ] **Step 4: Implement WebUI editors**

Add a text/card select, grouped template cards, textarea fields, variable chips/help text, restore-default buttons, and one save action. Use existing custom styling, theme variables, and status handling. Loading preferences must preserve user edits until a successful save response.

- [ ] **Step 5: Run focused WebUI/API tests and verify responsive markup**

Run: `node --test tests/test_login.mjs tests/test_management.mjs; $env:PYTHONPATH='..'; python -m unittest discover -s tests -p 'test_web_api_integration.py' -v`
Expected: all focused tests pass.

### Task 4: Correct metadata, command descriptions, license, and handoff documentation

**Files:**
- Modify: `main.py`, `metadata.yaml`, `README.md`
- Create: `LICENSE`, `PROJECT_STRUCTURE.md`
- Test: `tests/test_package.py`, `tests/test_runtime_contract.py`

**Interfaces:**
- Plugin metadata and registration report author `486`, version `0.3.0`, accurate command list, and repository URL.
- Root documentation explains installation, commands, template configuration, variables, and module layout.

- [ ] **Step 1: Add failing metadata/documentation tests**

Assert version synchronization, author `486`, presence of MIT license text, presence of `PROJECT_STRUCTURE.md`, and documentation entries for English/Chinese help plus message variables.

- [ ] **Step 2: Run the focused package tests and verify failures**

Run: `$env:PYTHONPATH='..'; python -m unittest discover -s tests -p 'test_package.py' -v; python -m unittest discover -s tests -p 'test_runtime_contract.py' -v`
Expected: author/version/license/documentation assertions fail.

- [ ] **Step 3: Update metadata and AstrBot command descriptions**

Set registration author/version to `486`/`0.3.0`. Add descriptions through the AstrBot-supported command metadata mechanism without changing command names or aliases; if the installed API supports only decorator descriptions, use that form consistently.

- [ ] **Step 4: Add MIT license and plain-language structure guide**

Create `LICENSE` with the standard MIT text and copyright holder `486`. Create `PROJECT_STRUCTURE.md` with a concise tree covering root files, `core/`, `rendering/`, `services/`, `web/`, `sources/`, `views/`, and `tests/`. Update README with the current command names and template setup.

- [ ] **Step 5: Run focused documentation tests**

Run: `$env:PYTHONPATH='..'; python -m unittest discover -s tests -p 'test_package.py' -v; python -m unittest discover -s tests -p 'test_runtime_contract.py' -v`
Expected: all focused tests pass.

### Task 5: Version, full verification, and publish the test branch

**Files:**
- Verify: all plugin files and generated test output.

- [ ] **Step 1: Run the full Python suite**

Run: `$env:PYTHONPATH='..'; python -m unittest discover -s tests -v`
Expected: all Python tests pass.

- [ ] **Step 2: Run all WebUI tests and compile Python**

Run: `node --test tests/test_login.mjs tests/test_management.mjs; python -m compileall -q .`
Expected: all Node tests pass and compilation exits 0.

- [ ] **Step 3: Audit diff and sensitive content**

Run `git diff --check`, inspect `git diff --stat`, search for stale `Aut-sep`, old `0.2.14`, hard-coded help/reminder strings, unknown template keys, conflict markers, and credential-like values. Confirm no server data or private tokens entered the repository.

- [ ] **Step 4: Commit and push the feature branch**

Commit with a message describing configurable message templates and metadata/docs updates, then push `codex/custom-message-templates` to the GitHub repository. Do not merge into `main` until the user tests the branch.
