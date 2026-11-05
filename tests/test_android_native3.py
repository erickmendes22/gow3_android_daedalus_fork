"""Host execution of native regression tests for the selective android3 port."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Android3NativeTests(unittest.TestCase):
    def test_native_settings_pad_edges_and_dialogs(self):
        cc, cxx = shutil.which('cc'), shutil.which('g++')
        if not cc or not cxx:
            self.skipTest('Host C/C++ compiler unavailable')
        cases = [
            (cxx, '-std=c++20', ['tests/test_graphics_settings.cpp', 'gpu/shim/gow3_settings.cpp']),
            (cxx, '-std=c++20', ['tests/test_pad_input.cpp']),
            (cc, '-std=c11', ['tests/test_services.c']),
        ]
        with tempfile.TemporaryDirectory() as directory:
            for index, (compiler, standard, sources) in enumerate(cases):
                executable = str(Path(directory) / f'test-{index}')
                built = subprocess.run([compiler, standard, '-O2', '-Wall', '-Wextra', '-Werror',
                                        '-pthread', '-I.', '-Isrc', '-Igpu/shim', *sources, '-o', executable],
                                       cwd=ROOT, capture_output=True, text=True, timeout=60)
                self.assertEqual(built.returncode, 0, built.stderr)
                ran = subprocess.run([executable], cwd=directory, capture_output=True, text=True, timeout=30)
                self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
