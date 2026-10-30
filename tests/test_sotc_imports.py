# SPDX-License-Identifier: GPL-2.0-or-later
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
class SotcNidTableTest(unittest.TestCase):
    def test_required_original_sotc_nids(self):
        source=(ROOT/'src/sotc_import_names.inc').read_text()
        entries=dict(re.findall(r'\{"([^"]+)","([^"]+)"\}',source))
        self.assertEqual(entries['hVYD7Ou2pCQ'],'_sceFiberInitializeImpl')
        self.assertEqual(entries['WB66evu8bsU'],'sceKernelGetCompiledSdkVersion')
        self.assertEqual(entries['pztV4AF18iI'],'sincosf')
        self.assertGreater(len(entries),300)
    def test_preserves_gow3_scoped_nid_list(self):
        original=(ROOT/'src/import_names.inc').read_text()
        self.assertIn('bzQExy189ZI#libc',original)
        runtime=(ROOT/'src/runtime.c').read_text()
        self.assertIn('sotc_import_names.inc',runtime)
        self.assertIn('SOTC_PORT',runtime)
if __name__=='__main__':
    unittest.main()
