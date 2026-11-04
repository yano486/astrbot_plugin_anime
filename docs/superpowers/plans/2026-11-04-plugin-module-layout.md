# Plugin Module Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move implementation modules into responsibility-based packages while preserving AstrBot plugin loading and behavior.

**Architecture:** Keep the AstrBot entry point and package metadata at repository root. Move domain/persistence/time modules to `core/`, formatting and image rendering to `rendering/`, refresh and reminder code to `services/`, and API/server code to `web/`; retain `sources/`, `tests/`, and `views/`.

**Tech Stack:** Python 3.10+, unittest, Node.js test runner, AstrBot plugin loader.

**Spec:** `docs/superpowers/specs/2026-11-04-plugin-module-layout-design.md`

## Global Constraints

- Keep `main.py`, `__init__.py`, `metadata.yaml`, `_conf_schema.json`, and `requirements.txt` at the repository root.
- Preserve existing `sources/`, `tests/`, and `views/` directories.
- Do not change command names, configuration keys, UI assets, source data, persistent data paths, or runtime behavior.
- Keep `from astrbot_plugin_anime import AnimePlugin` working through the root lazy export.
- Keep `PLUGIN_VERSION` and `metadata.yaml` synchronized; increment patch version from `0.2.12` to `0.2.13`.
- Measure regular files under the plugin root excluding `.git` after migration and report bytes and human-readable size.

---

### Task 1: Lock the plugin package contract

**Files:**
- Modify: `tests/test_package.py`

**Interfaces:**
- Consumes: existing root lazy export `astrbot_plugin_anime.AnimePlugin`.
- Produces: a regression test asserting the expected package files exist and moved modules no longer live at root.

- [ ] **Step 1: Add a failing package-layout test**

Add a test that checks the root still contains `main.py`, `__init__.py`, `metadata.yaml`, `_conf_schema.json`, and `requirements.txt`; that `core`, `rendering`, `services`, and `web` contain `__init__.py`; that the new module files exist; that old implementation module files are absent from root; and that `from astrbot_plugin_anime import AnimePlugin` still resolves.

- [ ] **Step 2: Run the test to verify the expected failure**

Run: `$env:PYTHONPATH='..'; python -m unittest discover -s tests -p 'test_package.py' -v`
Expected: the layout assertion fails because the responsibility packages have not been moved yet.

- [ ] **Step 3: Keep the test focused on the public entry and filesystem layout**

Do not assert implementation details or serialized behavior; the test only guards AstrBot's root entry and the agreed directory boundaries.

### Task 2: Move implementation modules and repair imports

**Files:**
- Create: `core/__init__.py`, `rendering/__init__.py`, `services/__init__.py`, `web/__init__.py`
- Move: `diagnostics.py`, `merge.py`, `models.py`, `schedule_utils.py`, `store.py`, `time_utils.py` to `core/`
- Move: `formatters.py`, `push_tables.py` to `rendering/`
- Move: `services.py` to `services/refresh.py`; `scheduler.py` to `services/scheduler.py`
- Move: `web_api.py` to `web/api.py`; `web_server.py` to `web/server.py`
- Modify: `main.py`, all affected modules under `sources/`, all tests importing moved modules
- Modify: `metadata.yaml`, `main.py`

**Interfaces:**
- Consumes: the package map in the spec.
- Produces: imports rooted at `core`, `rendering`, `services`, and `web`; unchanged root plugin class export.

- [ ] **Step 1: Create package initializer files**

Create empty `__init__.py` files in `core/`, `rendering/`, `services/`, and `web/`.

- [ ] **Step 2: Move the modules with Git-aware renames**

Run `git mv` for each source file listed above, preserving all file contents.

- [ ] **Step 3: Update production imports**

Update `main.py`, moved modules, and `sources/` imports using package-relative paths. In particular, source adapters import domain models/diagnostics through `..core`; rendering modules import models/time through `..core`; services import core and rendering through `..core` and `..rendering`; `web/server.py` imports `web/api.py` through `.api`.

- [ ] **Step 4: Update tests to import the new locations**

Change test imports from old root paths (`models`, `merge`, `store`, `time_utils`, `scheduler`, `services`, `web_api`, `web_server`, `push_tables`, `formatters`, `diagnostics`, `schedule_utils`) to the corresponding new subpackages. Leave AstrBot stub paths and plugin name imports unchanged.

- [ ] **Step 5: Bump the synchronized patch version**

Set `PLUGIN_VERSION = "0.2.13"` in `main.py` and `version: 0.2.13` in `metadata.yaml`.

- [ ] **Step 6: Run focused package and import tests**

Run: `$env:PYTHONPATH='..'; python -m unittest discover -s tests -p 'test_package.py' -v`
Expected: all package-layout and root-entry assertions pass.

### Task 3: Verify behavior, package integrity, and final footprint

**Files:**
- Verify: all tracked plugin files and package imports; no additional runtime changes.

**Interfaces:**
- Consumes: the migrated module graph and package contract from Tasks 1-2.
- Produces: verified test results, clean import references, and measured source footprint excluding `.git`.

- [ ] **Step 1: Run the complete Python test suite**

Run: `$env:PYTHONPATH='..'; python -m unittest discover -s tests -v`
Expected: all Python tests pass.

- [ ] **Step 2: Run all WebUI tests**

Run: `node --test tests/test_login.mjs tests/test_management.mjs`
Expected: all login and management tests pass without failures.

- [ ] **Step 3: Compile all Python modules**

Run: `python -m compileall -q .`
Expected: exit code 0.

- [ ] **Step 4: Audit stale module references and the final diff**

Run `rg` for imports of removed root module paths, then run `git diff --check` and `git diff --find-renames --stat`. Confirm that only module moves, import updates, package tests, and the version bump changed.

- [ ] **Step 5: Measure the plugin source tree**

Sum regular-file byte sizes recursively below the plugin root while excluding `.git`; also calculate MiB as bytes divided by 1,048,576. Report both and state explicitly that Git history is excluded.
