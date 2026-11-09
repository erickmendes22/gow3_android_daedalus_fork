"""Draw profiling must preserve the original Vulkan command stream."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text()
P = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_mali_perf_stats.h").read_text()
DRAW = D.split("void Rasterizer::DrawRecord(", 1)[1].split("void Rasterizer::DrawIndirect(", 1)[0]

class DrawProfiler(unittest.TestCase):
    def test_separate_subphases_on_one_of_256_draws(self):
        self.assertIn("SampleDrawPhases()", DRAW)
        self.assertIn("(++draws & 255u) == 0", P)
        self.assertIn("static_assert(std::size(names) == static_cast<unsigned>(Stage::Count))", P)
        for name in ("DrawTargets", "DrawBindings", "DrawBeginPass", "DrawInputs",
                     "DrawDescriptors", "DrawDynamic", "DrawCommands"):
            self.assertIn("MaliPerfStats::Stage::" + name, DRAW)
        self.assertIn('" vk_draw_commands_recorded=%llu empty_draw_candidates=%llu"', P)
        self.assertIn("CountDrawRecorded(square ? 2u : 1u)", DRAW)

    def test_gpu_correctness_is_not_altered(self):
        for statement in ("PrepareRenderState(pipeline);", "BindResources(pipeline);",
            "BeginRendering(pipeline);", "ResolveVertexBuffers(pipeline, draw_prepared);",
            "EmitVertexBuffers();", "pipeline->BindResources(set_writes, push_data);",
            "UpdateDynamicState(pipeline, is_indexed);", "scheduler.BeginRendering(state);",
            "cmdbuf.drawIndexed(num_indices, num_instances, 0, s32(first_vertex),",
            "cmdbuf.draw(num_indices, num_instances, first_vertex, first_instance);",
            "predication.EndDraw(cmdbuf, zpass_query, pred.predicated, predicate_state);"):
            self.assertIn(statement, DRAW)
        # No draw removed until its effect on occlusion/predication is proven.
        self.assertIn("CountEmptyDrawCandidate()", DRAW)
        self.assertNotIn("return; // empty draw", DRAW)

if __name__ == "__main__":
    unittest.main()
