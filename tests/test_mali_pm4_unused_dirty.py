"""PM4 dirty-register bitsets are needed only by two-stage draw recording."""
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]
C = (ROOT / "gpu/shadps4/video_core/amdgpu/liverpool.cpp").read_text()
H = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.h").read_text()
R = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text()
S = (ROOT / "tools/android/bionic/run-bionic.sh").read_text()

class DirtyRegisterTests(unittest.TestCase):
    def test_direct_draws_do_not_need_dirty_bitsets(self):
        self.assertIn("HasDrawPipe() const noexcept", H)
        self.assertIn("return draw_pipe != nullptr;", H)
        self.assertIn("rasterizer->HasDrawPipe()) || force_dirty", C)
        self.assertIn("AmdGpu::RegDirty* const draw_dirty =", C)
        self.assertIn("ApplyGraphicsRegisterPacket(regs, header, gfx_reg_checksum, draw_dirty,", C)
        self.assertIn("auto& dirty = liverpool->pipe_dirty;", R)
        self.assertIn("GOW3_PM4_DIRTY_ALWAYS", C)
        self.assertIn("GOW3_PM4_DIRTY_ALWAYS=${GOW3_PM4_DIRTY_ALWAYS:-0}", S)

    def test_mutations_remain_unconditional(self):
        apply = C.split("void Liverpool::ApplyGraphicsRegisterPacket(", 1)[1].split("// gow3: GOW3_DCB_STATS", 1)[0]
        self.assertIn("std::memcpy(&regs.reg_array", apply)
        self.assertIn("regs.SetDefaults();", apply)
        self.assertIn("regs.num_indices = draw_index->index_count;", apply)
        self.assertIn("if (dirty)", apply)
        self.assertIn("if (update_checksum)", apply)

if __name__ == "__main__":
    unittest.main()
