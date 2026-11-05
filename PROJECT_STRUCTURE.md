# Project Structure

This repository is an AstrBot plugin. The root keeps the files AstrBot needs to discover and install the plugin.

```text
astrbot_plugin_anime/
  main.py              AstrBot entry point and command handlers
  __init__.py          Lazy public plugin export
  metadata.yaml        Plugin name, author, version, and tags
  _conf_schema.json    AstrBot plugin configuration fields
  requirements.txt     Python dependencies
  core/                Shared models, storage, time handling, merge logic, and diagnostics
  rendering/           Text templates, message formatters, and image table rendering
  services/            Catalog refresh and reminder scheduling
  web/                 Embedded AstrBot API and standalone remote WebUI server
  sources/              Bangumi, bgmlist, and YUC source adapters
  views/               WebUI HTML, JavaScript, CSS, and login assets
  tests/               Python and Node.js regression tests
  docs/                Design and implementation notes for maintainers
```

## Where to start

- Change commands or command replies in `main.py` and `rendering/templates.py`.
- Change reminder text formatting in `rendering/formatters.py`.
- Change saved WebUI preferences and validation in `core/store.py` and `web/api.py`.
- Change data-source behavior in `sources/` and refresh orchestration in `services/refresh.py`.
- Run the Python suite with `PYTHONPATH=.. python -m unittest discover -s tests -v`.
- Run the WebUI suite with `node --test tests/test_login.mjs tests/test_management.mjs`.
