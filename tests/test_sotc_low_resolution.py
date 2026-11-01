#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Verify exact <720p guest dimension patches without claiming live GPU tests."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "ports/sotc/android/stage_sotc_lowres.py"
PREPARE = ROOT / "ports/sotc/android/prepare_game.py"
PACKAGE = ROOT / "ports/sotc/android/package_sotc_runtime.py"
JAVA = ROOT / "android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java"
UI = ROOT / "android-launcher/app/src/main/java/com/gow3/android/ui/SotcScreen.kt"

def import_script(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

stage = import_script(STAGE)
prep = import_script(PREPARE)


class SotcLowResolutionTest(unittest.TestCase):
    def test_upstream_render_validator_patched_in_runtime_copy(self):
        package = PACKAGE.read_text()
        self.assertIn("patch_sotc_lowres_modes(scripts/'sotc-upstream/scripts/sotc_modes.py')", package)
        source = STAGE.read_text()
        self.assertIn("w % 8 or h % 8", source)
        self.assertIn("w % 8 or h % 4", source)
        self.assertIn("if source.count(old) != 1:", source)
        fake = ("RENDER_SITES = []\n"
                "def render_patches(elf, ph, size):\n"
                "    if not (640 <= w <= 7680 and 360 <= h <= 4320) or w % 8 or h % 8:\n"
                "        raise SystemExit(f'render size {size}: 640x360 to 7680x4320, multiples of 8')\n"
                "    return writes\n")
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'sotc_modes.py'
            path.write_text(fake)
            stage.patch_sotc_lowres_modes(path)
            self.assertIn('or w % 8 or h % 4:', path.read_text())
            with self.assertRaises(ValueError):
                stage.patch_sotc_lowres_modes(path)

    @staticmethod
    def fake_patch(size, *, corrupt=None):
        w, h = [int(v) for v in size.split('x')]
        writes = []
        for address, length, which in prep.RENDER_DIMENSION_SITES:
            off = address - prep.RENDER_BASE + length - 4
            value = struct.pack('<I', w if which == 'W' else h)
            if corrupt == address:
                value = struct.pack('<I', 1280 if which == 'W' else 720)
            writes.append((off, value))
        data = struct.pack('<8sQQ', b'BBPATCH2', prep.RENDER_BASE, len(writes))
        for offset, value in writes:
            data += struct.pack('<QQ', offset, len(value)) + value
        return data

    def test_540p_360p_720p_requested_guest_dimensions(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'patches.bin'
            for size in ('960x540', '640x360', '1280x720'):
                path.write_bytes(self.fake_patch(size))
                prep.verify_render_patches(path, size)

    def test_lowres_cannot_silently_boot_with_incomplete_or_stale_patches(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'patches.bin'
            path.write_bytes(self.fake_patch('640x360', corrupt=0x004a2af2))
            with self.assertRaisesRegex(ValueError, "incomplete"):
                prep.verify_render_patches(path, '640x360')
            path.write_bytes(self.fake_patch('1280x720'))
            with self.assertRaisesRegex(ValueError, "incomplete"):
                prep.verify_render_patches(path, '960x540')
            path.write_bytes(b'broken')
            with self.assertRaisesRegex(ValueError, 'truncated'):
                prep.verify_render_patches(path, '640x360')

    def test_launcher_selector_wires_guest_540p_and_360p(self):
        java = JAVA.read_text()
        ui = UI.read_text()
        runner = (ROOT/'ports/sotc/android/run-sotc-bionic.sh').read_text()
        for menu, dims in (('360p','640x360'),('540p','960x540')):
            self.assertIn('case "'+menu+'": env.put("SOTC_RENDER","'+dims+'")', java)
            self.assertIn('"'+menu+'" to ', ui)
        self.assertIn('--render "$'+'{SOTC_RENDER:-1280x720}"', runner)
        self.assertIn("verify_render_patches(out/'patches.bin', render)", PREPARE.read_text())
        # VideoOut presentation remains 720p, only the guest render size changes.
        self.assertIn('env.put("SOTC_SCREEN_W","1280")', java)
        self.assertIn('env.put("SOTC_SCREEN_H","720")', java)


if __name__ == '__main__':
    unittest.main()
