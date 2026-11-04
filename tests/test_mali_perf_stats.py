"""Static validation for low-overhead automatically enabled Mali timings."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
GPU = ROOT / "gpu/shadps4/video_core"
SRC = (GPU / "renderer_vulkan/vk_mali_perf_stats.h").read_text()
PRES = (GPU / "renderer_vulkan/vk_presenter.cpp").read_text()
AHBH = (GPU / "renderer_vulkan/vk_swapchain_ahb.h").read_text()
AHB = (GPU / "renderer_vulkan/vk_swapchain_ahb.cpp").read_text()
TEX = (GPU / "texture_cache/texture_cache.cpp").read_text()
SH = (ROOT / "tools/android/bionic/run-bionic.sh").read_text()


class MaliPerfStatsTest(unittest.TestCase):
    def test_default_on_only_for_mali_cpu_present(self):
        self.assertIn("GOW3_MALI_PERF_STATS=${GOW3_MALI_PERF_STATS:-1}", SH)
        self.assertIn('std::getenv("GOW3_MALI_CPU_PRESENT")', SRC)
        self.assertIn('std::getenv("GOW3_MALI_PERF_STATS")', SRC)
        self.assertIn("(!option || option[0] != '0')", SRC)

    def test_sampled_and_coalesced(self):
        self.assertIn("frames.fetch_add(1, std::memory_order_relaxed)", SRC)
        self.assertIn("& 31u", SRC)
        self.assertIn("now_ms - last < 5000", SRC)
        self.assertIn('std::printf("%s\\n", line)', SRC)
        self.assertNotIn("std::thread", SRC)
        self.assertNotIn("fwrite(", SRC)
        self.assertNotIn("vkCmdWriteTimestamp", SRC)

    def test_present_substages_and_cross_module_flag(self):
        for stage in ["PrepareFrame", "FramesAheadWait", "AcquireAhb", "ReadbackSetup",
                      "ReadbackSubmit", "FenceWait", "Invalidate", "AhbTotal"]:
            self.assertIn("MaliPerfStats::Stage::" + stage, PRES)
        for stage in ["AhbLock", "AhbCopy", "AhbUnlock", "AhbIpc"]:
            self.assertIn("MaliPerfStats::Stage::" + stage, AHB)
        self.assertIn("u32 capture_frame = 0, bool perf_sample = false", AHBH)
        self.assertIn("frame->mali_capture_frame, mali_perf_sample", PRES)
        self.assertIn("MaliPerfStats::ReportIfDue()", PRES)

    def test_sync_dirty_download_and_gc(self):
        self.assertIn("MaliPerfStats::Stage::TextureGc", TEX)
        self.assertIn("MaliPerfStats::Stage::SyncTextureDownload", TEX)
        self.assertIn("scheduler.Finish();", TEX)
        self.assertIn("Vulkan::MaliPerfStats::SampleGc()", TEX)


if __name__ == "__main__":
    unittest.main()
