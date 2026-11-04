"""Android Mali: enable verified checksummed parallel draw preparation and safe inline texture memo."""
from pathlib import Path
import unittest
R=Path(__file__).resolve().parents[1]
SH=(R/"tools/android/bionic/run-bionic.sh").read_text()
DRAW=(R/"gpu/shadps4/video_core/renderer_vulkan/vk_draw_prep.cpp").read_text()
RAST=(R/"gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text()
HEAD=(R/"gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.h").read_text()
PM4=(R/"gpu/shadps4/video_core/amdgpu/liverpool.cpp").read_text()
PERF=(R/"gpu/shadps4/video_core/renderer_vulkan/vk_mali_perf_stats.h").read_text()
class MaliParallelDrawTest(unittest.TestCase):
    def test_preparation_workers_safely_opt_in_and_rollback(self):
        self.assertIn("GOW3_PREP_WORKERS=${GOW3_PREP_WORKERS:-4}", SH)
        self.assertIn("GOW3_MALI_INLINE_TEXTURE_SETS=${GOW3_MALI_INLINE_TEXTURE_SETS:-1}", SH)
        self.assertIn("GOW3_DRAW_PIPE", RAST)
        self.assertIn("constexpr u64 MaxScanLag = 64;", DRAW)
        self.assertIn("prepared->reg_checksum == liverpool->gfx_reg_checksum", RAST)
        self.assertIn("Gow3Threads::MakeBackground()", DRAW)
    def test_fast_path_keeps_aliasing_and_view_safety(self):
        self.assertIn("if (count == 0 || count > TextureSet::MaxImages", RAST)
        self.assertIn("ImageDescHash(sharp, image)", RAST)
        self.assertIn("hashes = inline_hashes.data();", RAST)
        self.assertIn("std::equal(set.hashes.begin(), set.hashes.begin() + count,", RAST)
        self.assertIn("set.generation == generation", RAST)
        self.assertIn("image.backing != entry.backing", RAST)
        self.assertIn("!texture_cache.IsUpToDate(entry.id)", RAST)
        self.assertIn("image.binding.is_target", RAST)
        self.assertIn("scene_targets->ProxyCurrent", RAST)
        self.assertIn("Gow3Toggle::Disabled(Gow3Toggle::TextureSetMemo)", RAST)
        self.assertIn("std::array<TextureSet, 32768> texture_sets{}", HEAD)
    def test_sample_guest_pm4_submit_wall(self):
        self.assertIn("MaliPerfStats::Stage::Pm4SubmitWall", PM4)
        self.assertIn("MaliPerfStats::SamplePm4Submit()", PM4)
        self.assertIn('"pm4_submit_wall"', PERF)
        self.assertIn("(++submits & 31u) == 0", PERF)
if __name__=="__main__": unittest.main()
