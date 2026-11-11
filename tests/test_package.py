from __future__ import annotations

import re
import unittest
from pathlib import Path

from support import install_astrbot_stubs

install_astrbot_stubs()


class PackageSmokeTests(unittest.TestCase):
    def test_plugin_package_exposes_main_class(self) -> None:
        from astrbot_plugin_anime import AnimePlugin

        self.assertEqual(AnimePlugin.__name__, "AnimePlugin")
        self.assertTrue(callable(AnimePlugin.current_season))

    def test_metadata_version_matches_plugin_registration_version(self) -> None:
        root = Path(__file__).resolve().parents[1]
        metadata = (root / "metadata.yaml").read_text(encoding="utf-8")
        source = (root / "main.py").read_text(encoding="utf-8")
        metadata_version = re.search(r"^version:\s*([^\s]+)", metadata, re.MULTILINE)
        source_version = re.search(r'^PLUGIN_VERSION\s*=\s*"([^"]+)"', source, re.MULTILINE)
        self.assertIsNotNone(metadata_version)
        self.assertIsNotNone(source_version)
        self.assertEqual(metadata_version.group(1), source_version.group(1))
        page = (root / "views" / "management" / "index.html").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r'\?v=([\d.]+)', page), [source_version.group(1)] * 4)
        self.assertIn(f'>v{source_version.group(1)}</span>', page)
        self.assertIn('author: !!str 486', metadata)
        self.assertIn('"0.3.22"', source)
        self.assertIn('register("astrbot_plugin_anime", "486"', source)
        self.assertIn("MIT License", (root / "LICENSE").read_text(encoding="utf-8"))
        self.assertTrue((root / "PROJECT_STRUCTURE.md").is_file())

    def test_plugin_entry_and_responsibility_packages_are_stable(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for name in ("main.py", "__init__.py", "metadata.yaml", "_conf_schema.json", "requirements.txt"):
            with self.subTest(root_file=name):
                self.assertTrue((root / name).is_file())

        expected_files = {
            "core": ("diagnostics.py", "merge.py", "models.py", "schedule_utils.py", "store.py", "time_utils.py"),
            "rendering": ("formatters.py", "push_tables.py"),
            "services": ("refresh.py", "scheduler.py", "table_scheduler.py"),
            "web": ("api.py", "server.py"),
        }
        for package, files in expected_files.items():
            with self.subTest(package=package):
                self.assertTrue((root / package / "__init__.py").is_file())
                for filename in files:
                    self.assertTrue((root / package / filename).is_file())

        for old_name in (
            "diagnostics.py", "formatters.py", "merge.py", "models.py", "push_tables.py",
            "schedule_utils.py", "scheduler.py", "services.py", "store.py", "time_utils.py",
            "web_api.py", "web_server.py",
        ):
            with self.subTest(old_root_module=old_name):
                self.assertFalse((root / old_name).exists())

        from astrbot_plugin_anime import AnimePlugin

        self.assertEqual(AnimePlugin.__name__, "AnimePlugin")


if __name__ == "__main__":
    unittest.main()
