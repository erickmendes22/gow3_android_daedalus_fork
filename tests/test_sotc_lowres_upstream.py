#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""End-to-end SotC render-site generation using the pinned original script.

Runs without proprietary eboot data: synthesize only known, publicly documented
instruction bytes from the upstream RENDER_SITES table, then prove the patched
540p and existing 360p modes emit the correct size at EVERY original site.
"""
import importlib.util
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_SCRIPTS = ROOT / "upstream-sotc/scripts"
STAGER_PATH = ROOT / "ports/sotc/android/stage_sotc_lowres.py"

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

stage = load(STAGER_PATH, "stage_sotc_lowres_test")

@unittest.skipUnless(UPSTREAM_SCRIPTS.is_dir(), "Pinned upstream checkout required")
class SotcPinnedLowResTest(unittest.TestCase):
    def test_full_pinned_sotc_render_patches_emit_real_guest_values(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "sotc_modes.py"
            shutil.copy2(UPSTREAM_SCRIPTS / "sotc_modes.py", source)
            stage.patch_sotc_lowres_modes(source)
            sys.path.insert(0, str(UPSTREAM_SCRIPTS))
            try:
                modes = load(source, "sotc_modes_540p_test")
            finally:
                sys.path.pop(0)
            self.assertGreater(len(modes.RENDER_SITES), 25)
            end_addr = max(address-modes.BASE+len(bytes.fromhex(original))
                           for address, kind, original in modes.RENDER_SITES)
            elf = bytearray(end_addr+32)
            for addr, _, original in modes.RENDER_SITES:
                orig = bytes.fromhex(original)
                offset = addr - modes.BASE
                elf[offset:offset+len(orig)] = orig
            ph = [{"type": 1, "vaddr": 0, "offset": 0, "filesz": len(elf)}]
            for width,height in ((640,360), (960,540), (1280,720)):
                with self.subTest(resolution=(width,height)):
                    result = dict(modes.render_patches(elf,ph,f"{width}x{height}"))
                    self.assertEqual(len(result),len(modes.RENDER_SITES))
                    for addr,kind,original in modes.RENDER_SITES:
                        old = bytes.fromhex(original)
                        data_len = 4
                        offset = addr - modes.BASE + len(old) - data_len
                        expected = {
                            'W': struct.pack('<I',width), 'H': struct.pack('<I',height),
                            'w': struct.pack('<f',width), 'h': struct.pack('<f',height),
                            'w2': struct.pack('<f',width/2), 'h2': struct.pack('<f',height/2),
                            'a': struct.pack('<f',width/height),
                            'P': struct.pack('<I',modes.render_pool(width,height)),
                            'v': struct.pack('<f',1080*width/height),
                        }[kind]
                        self.assertEqual(result[offset],expected,hex(addr))
            for invalid in ("960x539","638x360","960x542"):
                with self.assertRaises(SystemExit):
                    modes.render_patches(elf,ph,invalid)

if __name__ == "__main__":
    unittest.main()
