"""Verify compiler patch is deterministic and no CPU FEX/TSO fallback is emitted."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/"ports/sotc/android/aot/patch_bbrecomp_lowering.py"
spec=importlib.util.spec_from_file_location("sotc_lower",P)
patcher=importlib.util.module_from_spec(spec)
spec.loader.exec_module(patcher)

class LoweringPatchTests(unittest.TestCase):
    def test_pinned_upstream_anchor_and_three_real_implementations(self):
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp)/"lower_vector.cpp"
            src.write_text("using namespace llvm;\nbool Lower::emitVectorOp() {\n  switch (op->Op) {\n  case OP_VLOADTWOGPRS: {\n  return true;\n}\n}\n}\n")
            result=patcher.patch(src)
            patched=src.read_text()
            self.assertTrue(result["masked_load"])
            self.assertTrue(result["masked_store"])
            self.assertTrue(result["pcmpistrx"])
            self.assertIn("case OP_VLOADVECTORMASKED:",patched)
            self.assertIn("case OP_VSTOREVECTORMASKED:",patched)
            self.assertIn("case OP_VPCMPISTRX:",patched)
            self.assertIn("B.CreateCondBr(active, loadBB, doneBB)",patched)
            self.assertIn("B.CreateCondBr(active, storeBB, doneBB)",patched)
            self.assertIn("loaded->setVolatile(true)",patched)
            self.assertIn("store->setVolatile(true)",patched)
            self.assertIn("B.CreateICmpSLT(mask, ConstantInt::get(elemTy, 0))",patched)
            self.assertIn("case OP_VLOADTWOGPRS: {",patched)
            self.assertIn("SOTC_AOT_MASKED_SSE42_JTRODATA_NO_TSO_2",patched)
            self.assertNotIn("bbr_trap(",patched)
            self.assertNotIn("FEXCore::CPU::",patched)
            self.assertNotIn("--tso",patched.lower())
            with self.assertRaises(ValueError):
                patcher.patch(src)

    def test_incomplete_or_unknown_compiler_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp)/"lower_vector.cpp"
            src.write_text("unknown compiler code")
            with self.assertRaises(ValueError):
                patcher.patch(src)

    def test_full_sse42_aggregations_polarities_and_flags(self):
        src=patcher.STRING_COMPARE
        for mode in ("equal-any","unsigned/signed ranges","equal-each",
                     "equal-ordered"):
            self.assertIn(mode,src)
        for key in ("lhsLength","rhsLength","signedChar","polarity",
                    "flag(sf,31)","flag(zf,30)","flag(cf,29)","flag(of,28)"):
            self.assertIn(key,src)

if __name__=="__main__":
    unittest.main()
