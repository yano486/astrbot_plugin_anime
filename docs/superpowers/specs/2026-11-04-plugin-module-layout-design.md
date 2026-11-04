# Plugin Module Layout Design

## Goal

Organize the plugin's Python implementation into responsibility-based packages so the GitHub repository root is easier to scan, without changing runtime behavior or AstrBot's plugin entry point.

## Current Constraints

- AstrBot loads the plugin from the repository root; keep `main.py`, `__init__.py`, `metadata.yaml`, `_conf_schema.json`, and `requirements.txt` at that root.
- Preserve the existing `sources/`, `tests/`, and `views/` directories.
- Keep source data files, UI assets, command names, configuration keys, and persistent data paths unchanged.
- Do not merge modules into larger files; move cohesive modules and update package-relative imports.
- Keep the plugin version synchronized between `main.py` and `metadata.yaml` and increment the patch version for this published structural release.

## Target Layout

```text
astrbot_plugin_anime/
  __init__.py
  main.py
  metadata.yaml
  _conf_schema.json
  requirements.txt
  core/
    __init__.py
    diagnostics.py
    merge.py
    models.py
    schedule_utils.py
    store.py
    time_utils.py
  rendering/
    __init__.py
    formatters.py
    push_tables.py
  services/
    __init__.py
    refresh.py
    scheduler.py
  web/
    __init__.py
    api.py
    server.py
  sources/
  tests/
  views/
```

`main.py` remains the AstrBot integration boundary. `core/` owns shared domain types, persistence, time, merge, and diagnostics; `services/` owns refresh orchestration and reminder scheduling; `web/` owns API and HTTP server integration; `rendering/` owns message formatting and image generation. Source adapters, their fixtures, tests, translations, and management assets remain in their current directories.

## Import and Compatibility Rules

- Update every production and test import to the new package locations.
- Keep `from astrbot_plugin_anime import AnimePlugin` working through the root `__init__.py` lazy export.
- Do not keep one-line root shims for moved private modules; they would preserve the clutter this change is meant to remove and these module paths are not the documented plugin API.
- AstrBot-specific metadata and view discovery stay rooted at the plugin directory; only Python module locations change.
- `StarTools.get_data_dir()` and all persisted filenames remain unchanged.

## Validation

- Add/update package-layout tests that verify the root plugin entry imports, moved packages resolve, and moved implementation modules no longer remain at the repository root.
- Run all Python tests with the repository parent on `PYTHONPATH`.
- Run both Node WebUI test files and `python -m compileall -q .`.
- Inspect the final Git diff with rename detection and confirm no data/config/UI files changed beyond required import references and version metadata.
- Measure plugin source footprint after the move by summing regular non-`.git` files; report bytes and a human-readable size separately from Git history.
