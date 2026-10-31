#!/usr/bin/env python3
"""Exact user-provided GameHub 26.3/DD Turnip packaging smoke tests."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ports/sotc/android"))
from vendor_turnip import embed_verified_turnip, ARCHIVE_RELATIVE, LIB_SHA256


class SotcVendorTurnip(unittest.TestCase):
    def test_absent_vendor_zip_is_safe_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage = Path(tmp)
            self.assertFalse(embed_verified_turnip(stage,stage / "absent.zip"))
            self.assertFalse((stage / "sotcport/arm64/drivers/gamehub-dd").exists())

    def test_real_user_archive_if_supplied(self):
        archive = ROOT / ARCHIVE_RELATIVE
        if not archive.is_file():
            self.skipTest("User Turnip binary not committed; import via GPU driver screen")
        with tempfile.TemporaryDirectory() as tmp:
            stage = Path(tmp)
            self.assertTrue(embed_verified_turnip(stage,archive))
            from hashlib import sha256
            driver = stage / "sotcport/arm64/drivers/gamehub-dd/libvulkan_freedreno.so"
            self.assertEqual(sha256(driver.read_bytes()).hexdigest(), LIB_SHA256)
            self.assertTrue((stage / "sotcport/licenses/NOTICE-GameHub-DD-Turnip.txt").is_file())

    def test_driver_selection_and_fallback_exist(self):
        runner = (ROOT / "ports/sotc/android/run-sotc-bionic.sh").read_text()
        manager = (ROOT / "android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GpuDriverManager.java").read_text()
        pkg = (ROOT / "ports/sotc/android/package_sotc_runtime.py").read_text()
        self.assertIn('gamehub-dd|system|custom)',runner)
        self.assertIn('driver=gen8',runner)
        self.assertIn("hasBundledGameHubDD", manager)
        self.assertIn("embed_verified_turnip(stage,vendor_zip)",pkg)
        self.assertIn("shutil.copy2(original/'bachata_perf.py'",pkg)


if __name__ == "__main__":
    unittest.main()
