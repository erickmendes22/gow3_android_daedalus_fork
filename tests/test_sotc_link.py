#!/usr/bin/env python3
from pathlib import Path
import unittest
import importlib.util

P=Path(__file__).resolve().parents[1]/"ports/sotc/android/verify_sotc_link.py"
spec=importlib.util.spec_from_file_location("verify_sotc_link",P)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class TestSotcLinkSymbols(unittest.TestCase):
    def test_undefined_and_defined_nm(self):
        self.assertEqual(m.dynamic_symbols(" U runtime_memory_copy_out\n U foo@ABI\n",False),
                         {"runtime_memory_copy_out","foo"})
        self.assertEqual(m.dynamic_symbols("00000110 T bbgpu_init\n00000020 D bbgpu_count\n",True),
                         {"bbgpu_init","bbgpu_count"})
        self.assertEqual(m.dynamic_symbols("00000110 T bbgpu_init\n",False),set())
    def test_dso_requires_correct_exports(self):
        self.assertIn("bbgpu_init",m.EXPORTS)
        self.assertIn("libvulkan.so",m.ALLOWED)
        self.assertNotIn("libSDL3.so",m.ALLOWED)
if __name__=='__main__': unittest.main()
