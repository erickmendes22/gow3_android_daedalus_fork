"""Causal instrumentation must not alter draw/barrier semantics or add per-draw logging.

Native ARM64 renderer compilation remains the authoritative integration gate.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

def read(path):
    return (ROOT / path).read_text(encoding="utf-8")

class MaliCausalCounts(unittest.TestCase):
    def test_topology_counters_count_real_recorded_draws(self):
        raster = read("gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp")
        self.assertIn("void Rasterizer::DrawRecord(", raster)
        self.assertIn("void Rasterizer::DrawIndirectRecord(", raster)
        self.assertGreaterEqual(raster.count("MaliPerfStats::CountDrawTopology("), 2)
        self.assertIn("PrimitiveType::RectList", raster)
        self.assertIn("PrimitiveType::QuadList", raster)
        self.assertIn("Shader::SwStage::TessellationControl", raster)
        self.assertIn("Shader::SwStage::Geometry", raster)
    def test_barrier_counters_are_before_real_end_rendering(self):
        runtime = read("gpu/shadps4/video_core/renderer_vulkan/vk_runtime.cpp")
        scheduler = read("gpu/shadps4/video_core/renderer_vulkan/vk_scheduler.h")
        self.assertIn("MaliPerfStats::CountBarrierFlush(scheduler.IsRendering()", runtime)
        self.assertIn("bool IsRendering() const noexcept", scheduler)
        self.assertTrue(runtime.index("MaliPerfStats::CountBarrierFlush(scheduler.IsRendering()") <
                        runtime.index("scheduler.EndRendering();", runtime.index("void Runtime::FlushBarriers(")))
        self.assertIn("scheduler.Record([memory = memory_barrier", runtime)
    def test_compact_heartbeat_not_per_draw_printf(self):
        stats = read("gpu/shadps4/video_core/renderer_vulkan/vk_mali_perf_stats.h")
        self.assertIn("MALI_CAUSAL_COUNTS interval_ms=", stats)
        self.assertIn("pass_splits=%llu", stats)
        self.assertIn("ubo_bindings=%llu", stats)
        self.assertIn("CountUniformBinding()", stats)
        self.assertIn("if (!Enabled()) return;", stats)
        self.assertIn("std::memory_order_relaxed", stats)
        self.assertIn("counter.exchange(0", stats)
    def test_rebind_probe_covers_driver_image_creation_before_fallback(self):
        image = read("gpu/shadps4/video_core/texture_cache/image.cpp")
        stats = read("gpu/shadps4/video_core/renderer_vulkan/vk_mali_perf_stats.h")
        start = image.index("bool RebindRetiredImageMemory(")
        end = image.index("bool ReturnBcImage(", start)
        body = image[start:end]
        self.assertIn("Stage::ImageRebindProbe", body)
        self.assertIn("CountImageRebindCandidate()", body)
        self.assertIn("CountImageRebindIncompatible()", body)
        self.assertIn("CountImageRebindSuccess()", body)
        self.assertLess(body.index("CountImageRebindCandidate()"),
                        body.index("device.createImage(requested_ci)"))
        self.assertLess(body.index("CountImageRebindIncompatible()"),
                        body.index("device.destroyImage(new_image)", body.index("if (!retired.image)")))
        self.assertIn("image_rebind_probe", stats)
        self.assertIn("rebind_incompatible=%llu", stats)
        self.assertIn("rebind_success=%llu", stats)
        self.assertIn("GOW3_MALI_REBIND_RETIRED_MEMORY", body)
        self.assertNotIn("waitIdle(", body)

    def test_cpp_header_compiles(self):
        source = """
#include "video_core/renderer_vulkan/vk_mali_perf_stats.h"
int main() {
    Vulkan::MaliPerfStats::CountDrawTopology(true, false, false, false);
    Vulkan::MaliPerfStats::CountBarrierFlush(true, true, false, 2);
    Vulkan::MaliPerfStats::CountUniformBinding();
    return 0;
}
"""
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "causal.cpp"
            file.write_text(source)
            cmd = ["c++", "-std=c++20", "-Wall", "-Wextra", "-Werror",
                   "-Igpu/shadps4", "-fsyntax-only", str(file)]
            p = subprocess.run(cmd, cwd=ROOT, text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assertEqual(p.returncode, 0, p.stdout)

if __name__ == "__main__":
    unittest.main()
