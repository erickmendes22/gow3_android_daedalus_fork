"""Mali game menu CPU and image allocation stats are low overhead."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
GPU=ROOT/"gpu/shadps4/video_core/renderer_vulkan"
S=(GPU/"vk_mali_perf_stats.h").read_text()
R=(GPU/"vk_rasterizer.cpp").read_text()
P=(GPU/"vk_pipeline_cache.cpp").read_text()
I=(ROOT/"gpu/shadps4/video_core/texture_cache/image.cpp").read_text()

class MaliMenuMetricsTests(unittest.TestCase):
    def test_only_one_of_256_draws_timed(self):
        self.assertIn("(++draws & 255u) == 0",S)
        self.assertIn("MaliPerfStats::SampleDraw()",R)
        self.assertIn("MaliPerfStats::Stage::GpuDrawCpu",R)
        self.assertIn("MaliPerfStats::Stage::PipelineLookup",R)

    def test_compiler_and_image_allocation_timed_once(self):
        for stage in ["NewGraphicsPipeline","NewComputePipeline","NewShaderModule"]:
            self.assertIn("MaliPerfStats::Stage::"+stage,P)
        for stage in ["NewBcImage","NewRgba128Image","NewOtherImage"]:
            self.assertIn("MaliPerfStats::Stage::"+stage,I)
        self.assertIn("backing->image.size_bytes",I)
        self.assertIn("image_alloc_rgba128_mib",S)
        self.assertIn("image_alloc_bc_mib",S)
        self.assertIn("now_ms - last < 5000",S)

if __name__=="__main__":
    unittest.main()
