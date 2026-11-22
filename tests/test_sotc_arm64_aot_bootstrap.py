#!/usr/bin/env python3
"""Host regression of SotC BBPROBE5 to ARM64 AOT staging with TSO disabled."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"ports/sotc/android/aot/compile_local.py"
spec=importlib.util.spec_from_file_location("sotc_aot_compiler",SOURCE)
aot=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=aot
spec.loader.exec_module(aot)

def image_fixture(path, image:bytes, magic=b"BBPROBE5"):
    # <8s12Q> has 8 header+12 fields: (size,entry,segments,relocs,imports,flags,
    # procparam,tls[4],module_count), followed by 56B/module, 8B binding count,
    # segments (24B each), imports (128B each), relocations (32B each), image.
    fields=[len(image),0x10,1,0,0,0,0,0,0,0,0,1]
    blob=struct.pack("<8s12Q",magic,*fields)
    assert len(blob)==104
    path.write_bytes(blob+b"\0"*56+struct.pack("<Q",0)+b"\0"*24+image)

def patch_fixture(path, entries):
    contents=bytearray(struct.pack("<8sQQ",b"BBPATCH2",0x400000,len(entries)))
    for off,data in entries:
        contents+=struct.pack("<QQ",off,len(data))+data
    path.write_bytes(contents)

class TestSotcArm64Aot(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.boot=self.root/"boot-linked.bin"
        self.patches=self.root/"patches.bin"
        self.original=bytes(range(128))
        image_fixture(self.boot,self.original)
        patch_fixture(self.patches,[(12,b"\xaa\xbb"),(63,b"\xcc")])

    def test_aot_no_tso_codegen_and_no_false_runtime_claim(self):
        cmd=aot.compiler_command(Path("/compiler"),Path("/game"),self.boot,
              Path("/out/libSotcAot.so"),Path("/out/stats"),None,3,64)
        self.assertNotIn("--tso",cmd)
        self.assertIn("--resume-entries",cmd)
        self.assertIn("--no-callee-saved",cmd)
        self.assertIn("armv8.2",cmd)
        self.assertNotIn("--no-dirty-check",cmd)
        self.assertNotIn("--no-tso",cmd)
        self.assertEqual(aot.AOT_FLAGS,("--resume-entries","--no-callee-saved"))

    def test_prepared_image_precise_patches(self):
        out=self.root/"native-boot-linked.bin"
        info=aot.stage_native_boot(self.boot,self.patches,out)
        self.assertEqual(info["patch_count"],2)
        data=out.read_bytes()
        i=info["table_bytes"]
        self.assertEqual(data[i+12:i+14],b"\xaa\xbb")
        self.assertEqual(data[i+63],0xcc)
        self.assertEqual(data[i:i+12],self.original[:12])
        self.assertEqual(self.boot.read_bytes()[i:i+128],self.original)
        self.assertEqual(aot.boot_info(out)["image_bytes"],128)
        self.assertEqual(info["patched_image_sha256"],hashlib.sha256(data[info["table_bytes"]:]).hexdigest())

    def test_patch_offsets_are_image_relative_not_plus_0x400000(self):
        """BBPATCH2 header base is for relocatable POINTER VALUES, not patch offsets.
        Adding 0x400000 can overwrite FDE metadata instead of x86 code.
        """
        sample = bytearray(b"\0" * (aot.PATCH_BASE + 64))
        sample[0x30:0x38] = b"\x11" * 8
        sample[aot.PATCH_BASE + 0x30:aot.PATCH_BASE + 0x38] = b"\x22" * 8
        image_fixture(self.boot, bytes(sample))
        patch_fixture(self.patches, [(0x30, b"\x99" * 8)])
        out = self.root / "relative.BBPROBE5"
        info = aot.stage_native_boot(self.boot, self.patches, out)
        img = out.read_bytes()[info["table_bytes"]:]
        self.assertEqual(img[0x30:0x38], b"\x99" * 8)
        self.assertEqual(img[aot.PATCH_BASE+0x30:aot.PATCH_BASE+0x38], b"\x22"*8)

    def test_reject_overlap_and_overflow(self):
        patch_fixture(self.patches,[(12,b"hello"),(14,b"\x33")])
        with self.assertRaisesRegex(ValueError,"Overlapping"):
            aot.stage_native_boot(self.boot,self.patches,self.root/"bad.bin")
        patch_fixture(self.patches,[(127,b"toolong")])
        with self.assertRaisesRegex(ValueError,"outside image"):
            aot.stage_native_boot(self.boot,self.patches,self.root/"bad.bin")

    def test_reject_bad_image_signature_length(self):
        image_fixture(self.boot,self.original,b"G3PROBE5")
        with self.assertRaisesRegex(ValueError,"BBPROBE5"):
            aot.boot_info(self.boot)
        image_fixture(self.boot,self.original)
        with self.boot.open("ab") as f:f.write(b"garbage")
        with self.assertRaisesRegex(ValueError,"inconsistent"):
            aot.boot_info(self.boot)

    def test_reject_wrong_title_or_stale_game(self):
        game=self.root/"game";prepared=self.root/"prepared";game.mkdir();prepared.mkdir()
        (game/"eboot.bin").write_bytes(b"game-self")
        (game/"sce_sys").mkdir()
        (game/"sce_module").mkdir()
        for f in ("sce_sys/param.sfo","sce_module/libc.prx","sce_module/libSceFios2.prx"):
            (game/f).write_bytes(b"placeholder")
        (prepared/"analysis.json").write_text(json.dumps({"source_sha256":aot.sha256(game/"eboot.bin")}))
        (prepared/".sotc-android-prepare.json").write_text(json.dumps({"title_id":"CUSA08809"}))
        self.assertEqual(aot.validate_game(prepared,game)["title_id"],"CUSA08809")
        (game/"eboot.bin").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError,"does not match"):
            aot.validate_game(prepared,game)
        (prepared/".sotc-android-prepare.json").write_text(json.dumps({"title_id":"OTHER"}))
        (prepared/"analysis.json").write_text(json.dumps({"source_sha256":aot.sha256(game/"eboot.bin")}))
        with self.assertRaisesRegex(ValueError,"Unsupported"):
            aot.validate_game(prepared,game)

    def test_native_result_rejects_unsupported_ops(self):
        so=self.root/"libSotcAot.so";stats=self.root/"compile.txt";meta=self.root/"libSotcAot.json"
        so.write_bytes(b"\x7fELF"+b"\0"*14+struct.pack("<H",183))
        md={"abi_version":2,"compiler_version":"2",
            "so_sha256":aot.sha256(so),"unit_count":1000}
        meta.write_text(json.dumps(md))
        stats.write_text("units with bbr_trap (unsupported ops): 0 (0.0%)\n")
        self.assertEqual(aot.verify_native(so,stats,meta)["unit_count"],1000)
        md["compiler_version"]="2"  # SotC compiler v2 fixes out-of-function jump tables
        meta.write_text(json.dumps(md))
        self.assertEqual(aot.verify_native(so,stats,meta)["compiler_version"],"2")
        md["compiler_version"]="1"
        meta.write_text(json.dumps(md))
        with self.assertRaisesRegex(ValueError,"ABI/compiler"):
            aot.verify_native(so,stats,meta)
        md["compiler_version"]="5-tlou-tso-outlined-unaligned-v1"
        meta.write_text(json.dumps(md))
        with self.assertRaisesRegex(ValueError,"ABI/compiler"):
            aot.verify_native(so,stats,meta)
        md["compiler_version"]="2"
        meta.write_text(json.dumps(md))
        stats.write_text("LoadMemTSO\nunits with bbr_trap (unsupported ops): 0 (0.0%)\n")
        with self.assertRaisesRegex(ValueError,"Guest TSO operations"):
            aot.verify_native(so,stats,meta)
        stats.write_text("units with bbr_trap (unsupported ops): 1 (0.01%)\n")
        with self.assertRaisesRegex(ValueError,"fatal unsupported"):
            aot.verify_native(so,stats,meta)
        stats.write_text("units with bbr_trap (unsupported ops): 80 (8.0%)\n")
        with self.assertRaisesRegex(ValueError,"unsupported"):
            aot.verify_native(so,stats,meta)

    def test_compiler_not_executed_without_device_game(self):
        self.assertTrue("aot_execution_integrated" in SOURCE.read_text())
        self.assertTrue("fex_runtime_required_for_current_release" in SOURCE.read_text())

if __name__=="__main__":unittest.main()
