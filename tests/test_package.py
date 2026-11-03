from __future__ import annotations

import unittest

from support import install_astrbot_stubs

install_astrbot_stubs()


class PackageSmokeTests(unittest.TestCase):
    def test_plugin_package_exposes_main_class(self) -> None:
        from astrbot_plugin_anime import AnimePlugin

        self.assertEqual(AnimePlugin.__name__, "AnimePlugin")
        self.assertTrue(callable(AnimePlugin.current_season))


if __name__ == "__main__":
    unittest.main()
