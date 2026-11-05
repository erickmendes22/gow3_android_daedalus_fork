"""Detect host libraries in the cross-build link model before GPU compilation."""
from paths import ROOT
import importlib.util
from pathlib import Path
import shutil
import struct
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('bionic_link_audit',ROOT/'tools/android/bionic/audit_link.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

@unittest.skipUnless(shutil.which('readelf'),'readelf required')
class BionicLinkAudit(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.prefix=self.root/'android'
        self.build=self.root/'build'
        self.prefix.mkdir();self.build.mkdir()

    def elf(self,name,machine):
        p=self.prefix/name
        ident=b'\x7fELF\x02\x01\x01'+b'\0'*9
        p.write_bytes(struct.pack('<16sHHIQQQIHHHHHH',ident,3,machine,1,0,0,0,0,64,56,0,64,0,0))
        return p

    def audit(self,fragments):
        return module.audit(fragments,self.build,[self.prefix],shutil.which('readelf'))

    def test_accepts_arm64_and_generated_targets(self):
        p=self.elf('android.so',183)
        self.assertEqual(self.audit([
            {'role':'libraries','fragment':str(p)+' third_party/generated.a -latomic'},
            {'role':'flags','fragment':'-I/host/include'}]),1)

    def test_rejects_x86_64_even_inside_target_prefix(self):
        p=self.elf('host.so',62)
        with self.assertRaisesRegex(ValueError,'Non-ARM64'):
            self.audit([{'role':'libraries','fragment':str(p)}])

    def test_rejects_host_library_and_search_paths(self):
        for role,fragment in [('libraries',str(self.root/'host/libatomic.so')),
                              ('libraryPath','-L'+str(self.root/'host/lib'))]:
            with self.subTest(fragment=fragment), self.assertRaisesRegex(ValueError,'outside-target'):
                self.audit([{'role':role,'fragment':fragment}])

    def test_rejects_missing_imports(self):
        with self.assertRaisesRegex(ValueError,'Missing imported'):
            self.audit([{'role':'libraries','fragment':str(self.prefix/'missing.a')}])

    def test_accepts_ndk_arm64_atomic_placeholder(self):
        library=self.elf('android.so',183)
        stub=self.prefix/'aarch64/libatomic.a'
        stub.parent.mkdir()
        stub.write_text('/* __atomic functions are supplied by compiler builtins. */\n')
        self.assertEqual(module.audit([
            {'role':'libraries','fragment':str(library)+' '+str(stub)}],
            self.build,[self.prefix],shutil.which('readelf'),self.prefix),2)
