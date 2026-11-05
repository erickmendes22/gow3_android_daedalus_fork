"""Reject host toolchain leakage before cross-compiling Python extensions."""
from paths import ROOT
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    'bionic_python_audit', ROOT / 'tools/android/bionic/audit_python.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class BionicPythonAudit(unittest.TestCase):
    configuration = '''SOABI=cpython-313-aarch64-linux-android
EXT_SUFFIX=.cpython-313-aarch64-linux-android.so
MULTIARCH=aarch64-linux-android
CC=/target-ndk/bin/aarch64-linux-android30-clang
CPP=/target-ndk/bin/aarch64-linux-android30-clang -E
LIBLZMA_LIBS=
'''

    def audit(self, configuration):
        module.audit(configuration, Path('/target-ndk'))

    def test_accepts_android_configuration(self):
        self.audit(self.configuration)

    def test_rejects_host_abi(self):
        with self.assertRaisesRegex(ValueError, 'not Android ARM64'):
            self.audit(self.configuration.replace('aarch64-linux-android', 'x86_64-linux-gnu'))

    def test_rejects_host_preprocessor(self):
        with self.assertRaisesRegex(ValueError, 'CPP is not from the NDK'):
            self.audit(self.configuration.replace(
                'CPP=/target-ndk/bin/aarch64-linux-android30-clang -E',
                'CPP=/host/conda/bin/x86_64-linux-gnu-cpp'))

    def test_reads_preprocessor_from_configure_log(self):
        configuration = self.configuration.replace(
            'CPP=/target-ndk/bin/aarch64-linux-android30-clang -E\n', '')
        module.audit(configuration, '/target-ndk',
                     "CPP='/target-ndk/bin/aarch64-linux-android30-clang -E'\n")
        with self.assertRaisesRegex(ValueError, 'CPP is not from the NDK'):
            module.audit(configuration, '/target-ndk', "CPP='/host/conda/cpp'\n")

    def test_rejects_host_module_dependencies(self):
        for flag in ['-L/host/conda/lib -llzma', '-I/host/conda/include']:
            with self.subTest(flag=flag), self.assertRaisesRegex(ValueError, 'Host dependency'):
                self.audit(self.configuration + 'LIBLZMA_LIBS=' + flag + '\n')
