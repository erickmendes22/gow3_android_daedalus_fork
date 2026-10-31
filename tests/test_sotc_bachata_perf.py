#!/usr/bin/env python3
"""Bachata S4+ 0.2.7 guest patch regression suite (no PS4 game file in CI)."""
from pathlib import Path
import hashlib
import sys
import struct
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ports/sotc/android"))
from bachata_perf import (BASE, PATCHES, SHADOW_CAVES, EBOOT_SHA256,
                          _verify_calls, parse_effects, append_bachata_patches)


class BachataPerf(unittest.TestCase):
    @staticmethod
    def guest_image():
        # Small synthetic executable segment containing only the verified
        # original CALL sites. The cave bytes remain zero as in the real game.
        image = bytearray(0x1000000)
        for _, (_, _, calls) in PATCHES.items():
            for address, original, _ in calls:
                off = address - BASE
                image[off:off + len(bytes.fromhex(original))] = bytes.fromhex(original)
        ph = [dict(type=1, flags=5, vaddr=0, filesz=len(image), offset=0)]
        return image, ph

    def test_all_16_guest_writes_are_independent_and_well_formed(self):
        image, ph = self.guest_image()
        writes = _verify_calls(image, ph, tuple(PATCHES))
        self.assertEqual(len(writes), 16)
        self.assertEqual(len({a for a, _ in writes}), 16)
        self.assertTrue(all(a >= 0 and data for a, data in writes))

    def test_original_instruction_mismatch_rejects_patch(self):
        image, ph = self.guest_image()
        address = PATCHES["bloom"][2][0][0] - BASE
        image[address] ^= 0xff
        with self.assertRaisesRegex(ValueError, "unexpected original bytes"):
            _verify_calls(image, ph, ("bloom",))

    def test_occupied_code_cave_rejects_patch(self):
        image, ph = self.guest_image()
        image[PATCHES["fog"][0] - BASE] = 0xcc
        with self.assertRaisesRegex(ValueError, "occupied"):
            _verify_calls(image, ph, ("fog",))

    def test_unknown_and_duplicate_options(self):
        self.assertEqual(parse_effects("bloom, blur,bloom"), ("bloom", "blur"))
        self.assertEqual(parse_effects(""), ())
        with self.assertRaisesRegex(ValueError, "Unknown"):
            parse_effects("fakeshadow")

    def test_foreign_eboot_never_touches_native_patch_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "eboot.bin").write_bytes(b"fake")
            packed = struct.pack("<8sQQ", b"BBPATCH2", BASE, 0)
            out = path / "patches.bin"
            out.write_bytes(packed)
            with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
                append_bachata_patches(path, path / "eboot.bin",
                                       out, "CUSA08809", "bloom")
            self.assertEqual(out.read_bytes(), packed)

    def test_integration_scripts(self):
        prepare = (ROOT / "ports/sotc/android/prepare_game.py").read_text()
        package = (ROOT / "ports/sotc/android/package_sotc_runtime.py").read_text()
        run = (ROOT / "ports/sotc/android/run-sotc-bionic.sh").read_text()
        self.assertIn("append_bachata_patches(upstream,eboot,out/'patches.bin',title,perf_effects)", prepare)
        self.assertIn("shutil.copy2(original/'bachata_perf.py',scripts/'bachata_perf.py')", package)
        self.assertIn('--perf "$SOTC_BACHATA_PERF"', run)
        self.assertIn("export SOTC_ASYNC_SHADERS=0", run)


if __name__ == "__main__":
    unittest.main()
