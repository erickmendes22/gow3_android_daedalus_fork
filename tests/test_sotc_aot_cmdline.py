#!/usr/bin/env python3
"""No game data: verify SotC linked image + AOT command-line equivalence."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"ports/sotc/android/aot/cmdline_image.py"
spec=importlib.util.spec_from_file_location("sotc_cmdline",SCRIPT)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def image(length=0x7000,lea=0x1100):
    fields=[b"BBPROBE5",length,lea,2,0,0,1,0,0,0,0,8,2]
    # Two dummy linked-module structures, no native bindings or imports.
    body=bytearray(length)
    body[lea:lea+7]=b"\x48\x8d\x35\x00\x00\x00\x00"
    return (mod.HDR.pack(*fields)+b"\0"*(56*2)+struct.pack("<Q",0)
            +mod.SEG.pack(0,0x2000,5)+mod.SEG.pack(0x2000,0x5000,6)
            +body)

class SotcPrecompiledCmdlineTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        p=Path(t.name)
        self.source=p/"original.BBPROBE5"
        self.source.write_bytes(image())
        self.before=self.source.read_bytes()
        self.cmd=p/"cmdline.bin"
        self.cmd.write_bytes(mod.CMD.pack(b"SOTCCMD1",0x1100)+
                             b"+VSyncWindow=10% +TargetFramesPerSeconds=1")
        self.out=p/"native.BBPROBE5"

    def test_lea_points_into_new_rw_segment_and_original_unchanged(self):
        result=mod.embed(self.source,self.cmd,self.out)
        actual=self.out.read_bytes()
        fields,seg_at,segs,table_end=mod.header_info(actual)
        self.assertEqual(fields[3],3)
        self.assertEqual(segs[-1][2],6)
        self.assertEqual(segs[-1][0] % 16384,0, "16-KiB Android page alignment")
        self.assertEqual(result["segment_count"],3)
        self.assertEqual(result["cmdline_bytes"],len(self.cmd.read_bytes())-16)
        image=actual[table_end:]
        disp=struct.unpack_from("<i",image,0x1103)[0]
        dst=0x1107+disp
        self.assertEqual(dst,segs[-1][0])
        self.assertEqual(image[dst:dst+4],b"+VSync"[0:4])
        self.assertEqual(self.source.read_bytes(),self.before)

    def test_modified_command_line_changes_native_hash(self):
        a=mod.embed(self.source,self.cmd,self.out)
        self.cmd.write_bytes(mod.CMD.pack(b"SOTCCMD1",0x1100)+b"+TargetFramesPerSeconds=0")
        b=mod.embed(self.source,self.cmd,self.out)
        self.assertNotEqual(a["native_boot_sha256"],b["native_boot_sha256"])
        self.assertNotEqual(a["cmdline_sha256"],b["cmdline_sha256"])

    def test_rejects_invalid_lea(self):
        self.cmd.write_bytes(mod.CMD.pack(b"SOTCCMD1",0x1200)+b"hello")
        with self.assertRaisesRegex(ValueError,"signature mismatch"):
            mod.embed(self.source,self.cmd,self.out)

    def test_rejects_overwrite(self):
        with self.assertRaisesRegex(ValueError,"never overwrite"):
            mod.embed(self.source,self.cmd,self.source)

    def test_rejects_bad_guest_image(self):
        self.source.write_bytes(self.source.read_bytes()[:-1])
        with self.assertRaisesRegex(ValueError,"length mismatch"):
            mod.embed(self.source,self.cmd,self.out)

if __name__=="__main__":
    unittest.main()
