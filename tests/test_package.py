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


if __name__ == "__main__":
    unittest.main()
