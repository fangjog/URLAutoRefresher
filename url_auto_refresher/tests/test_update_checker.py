from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
APP_DIR = ROOT_DIR / "app"
sys.path.insert(0, str(APP_DIR))

from update_checker import (  # noqa: E402
    is_newer_version,
    normalize_version,
    select_download_asset,
)


class UpdateCheckerTest(unittest.TestCase):
    def test_normalize_version_strips_v_prefix(self) -> None:
        self.assertEqual(normalize_version("v1.2.3"), "1.2.3")
        self.assertEqual(normalize_version("V2.0.0"), "2.0.0")

    def test_version_comparison_pads_missing_parts(self) -> None:
        self.assertTrue(is_newer_version("1.0.1", "1.0.0"))
        self.assertTrue(is_newer_version("1.1", "1.0.9"))
        self.assertFalse(is_newer_version("1.0", "1.0.0"))
        self.assertFalse(is_newer_version("0.9.9", "1.0.0"))

    def test_select_download_asset_prefers_windows_package(self) -> None:
        assets = [
            {
                "name": "source-code.zip",
                "browser_download_url": "https://example.com/source-code.zip",
            },
            {
                "name": "URLAutoRefresher-win64.zip",
                "browser_download_url": "https://example.com/win64.zip",
            },
        ]

        self.assertEqual(select_download_asset(assets), "https://example.com/win64.zip")


if __name__ == "__main__":
    unittest.main()
