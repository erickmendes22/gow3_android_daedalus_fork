#!/usr/bin/env python3
"""Regression tests for SotC Android mksh /data/local here-document failure."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"ports/sotc/android/run-sotc-bionic.sh"
VERIFY=ROOT/"ports/sotc/android/aot/verify_compiler.py"
spec=importlib.util.spec_from_file_location("verify_compiler",VERIFY)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class AndroidMkshAotCompilerTests(unittest.TestCase):
    def test_launcher_never_uses_here_documents(self):
        shell=SCRIPT.read_text()
        self.assertNotIn("<<'PY'",shell)
        self.assertNotIn("<<PY",shell)
        self.assertIn('sotc_aot_verify_compiler.py',shell)
        self.assertIn('--compiler "$compiler" --manifest "$expected"',shell)
        self.assertIn('next="$base/user/.aot-next-$$"',shell)
        self.assertIn('backup="$base/user/.aot-backup-$$"',shell)

    def test_binary_checksum_and_elf_validated(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            elf=bytearray(4096)
            elf[:4]=b"\x7fELF"
            elf[4]=2
            elf[16:18]=(3).to_bytes(2,'little')
            elf[18:20]=(183).to_bytes(2,'little')
            elf[100:100+len(module.MARKER)]=module.MARKER
            binary=root/"libbbrecomp.so"
            binary.write_bytes(elf)
            manifest=root/"sotc-patched-compiler.sha256"
            manifest.write_text(hashlib.sha256(elf).hexdigest()+"  libbbrecomp.so\n")
            self.assertEqual(module.verify_compiler(binary,manifest)["status"],"verified")
            manifest.write_text("0"*64+"  libbbrecomp.so\n")
            with self.assertRaisesRegex(ValueError,"SHA256 differs"):
                module.verify_compiler(binary,manifest)
            manifest.write_text(hashlib.sha256(elf).hexdigest()+"\n")
            binary.write_bytes(b"not an ELF")
            with self.assertRaisesRegex(ValueError,"AArch64 ELF"):
                module.verify_compiler(binary,manifest)

if __name__=="__main__":
    unittest.main()
