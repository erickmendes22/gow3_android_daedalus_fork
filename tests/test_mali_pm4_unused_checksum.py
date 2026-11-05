"""Skip PM4 checksum only when no speculative draw preparation worker exists."""
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]
C = (ROOT / "gpu/shadps4/video_core/amdgpu/liverpool.cpp").read_text()
H = (ROOT / "gpu/shadps4/video_core/amdgpu/liverpool.h").read_text()
D = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_draw_prep.cpp").read_text()
R = (ROOT / "tools/android/bionic/run-bionic.sh").read_text()

class Pm4ChecksumTests(unittest.TestCase):
    def test_no_worker_skips_unconsumed_checksum(self):
        self.assertIn("if (draw_prep && !draw_prep->Enabled())", C)
        self.assertIn("const bool compute_checksum = (draw_prep && draw_prep->Enabled()) || force_checksum;", C)
        self.assertIn("ApplyGraphicsRegisterPacket(regs, header, gfx_reg_checksum, draw_dirty,", C)
        self.assertIn("if (update_checksum) {", C)
        self.assertIn("GOW3_PM4_CHECKSUM_ALWAYS", C)
        self.assertIn("GOW3_PM4_CHECKSUM_ALWAYS=${GOW3_PM4_CHECKSUM_ALWAYS:-0}", R)
        self.assertIn("bool update_checksum = true", H)

    def test_worker_and_compute_hashes_unchanged(self):
        self.assertIn("ApplyGraphicsRegisterPacket(*regs, header, checksum, &dirty)", D)
        self.assertIn("ApplyGraphicsRegisterPacket(*regs, header, checksum)", D)
        self.assertIn("if (checksum_needed) {", C)
        self.assertIn("rasterizer->GetDrawPreparation().Enabled()", C)

    def test_register_effects_are_not_removed(self):
        apply = C.split("void Liverpool::ApplyGraphicsRegisterPacket(", 1)[1].split("// gow3: GOW3_DCB_STATS", 1)[0]
        for marker in ("regs.SetDefaults()", "Regs::ContextRegWordOffset",
                       "Regs::ShRegWordOffset", "Regs::UconfigRegWordOffset", "regs.num_indices"):
            self.assertIn(marker, apply)
        self.assertLess(apply.index("std::memcpy(&regs.reg_array"), apply.index("if (update_checksum)"))
if __name__ == "__main__":
    unittest.main()
