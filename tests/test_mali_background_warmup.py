"""Safety guards for the Mali background pipeline-cache warmup path.

These checks protect the native rendering code paths against accidentally
reintroducing live shader metadata into the background precompiler.
An actual ARM64 compilation is required separately by the same workflow.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SERIAL = ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_pipeline_serialization.cpp"
COMPUTE = ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_compute_pipeline.h"


class MaliWarmupSafetyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.code = SERIAL.read_text(encoding="utf-8")
        cls.compute_code = COMPUTE.read_text(encoding="utf-8")

    def test_background_build_reads_snapshot_not_live_program(self):
        self.assertIn("stage->compile_info = std::make_unique<Shader::Info>(stage->program->info)", self.code)
        self.assertIn("stage->compile_info->user_data = {}", self.code)
        self.assertIn("const auto stage_refs = entry.stages;", self.code)
        self.assertIn("build_infos[i] = stage_refs[i]->compile_info.get()", self.code)
        self.assertIn("built.stage_refs = stage_refs;", self.code)
        self.assertIn("compute_key, *build_infos[0], modules[0]", self.code)
        self.assertIn("pipeline_cache, build_infos,", self.code)

    def test_published_pipelines_restore_live_stage_pointers(self):
        publish = self.code.index("for (auto& built : warm.built.Take(warm.mali ? 8 : 64))")
        rebind_graphics = self.code.index("built.graphics->PublishStages(built.live_infos)", publish)
        rebind_compute = self.code.index("built.compute->PublishStage(built.live_infos[0])", publish)
        insert = self.code.index("PublishFirst(graphics_pipelines", publish)
        self.assertLess(rebind_graphics, insert)
        self.assertLess(rebind_compute, insert)
        self.assertIn("void PublishStage(const Shader::Info* info)", self.compute_code)

    def test_reject_invalid_serialized_permutation(self):
        self.assertIn("stage.perm_idx >= Program::MaxPermutations", self.code)
        self.assertIn("entry.compute && (!infos[0] || !modules[0])", self.code)
        self.assertIn("std::ranges::none_of(modules", self.code)

    def test_mali_warmup_is_batched_without_dropping_entries(self):
        self.assertIn("warm.mali = mali;", self.code)
        self.assertIn("warm.mali && pump_started - warm.last_batch < 4ms", self.code)
        self.assertIn("warm.built.Take(warm.mali ? 8 : 64)", self.code)
        self.assertIn("warm.read.Take(warm.mali ? 8 : 32)", self.code)
        self.assertIn("warm.done.fetch_add(1, std::memory_order_relaxed)", self.code)
        self.assertIn("warm.pool->Push(", self.code)


    def test_cache_serialization_rejects_old_pointer_bearing_format(self):
        self.assertIn("ShaderMetaVersion = 8u", self.code)
        self.assertNotIn("info.Write(this, sizeof(InfoPersistent))", self.code)
        self.assertNotIn("info.Read(this, sizeof(Shader::InfoPersistent))", self.code)
        for name in ("buffers", "images", "samplers", "fmasks"):
            self.assertIn(f"info.Write({name});", self.code)
            self.assertIn(f"read_list({name},", self.code)
        self.assertIn("!spec.Deserialize(ar) || !info.Deserialize(ar)", self.code)

    def test_bad_cache_lengths_cannot_overflow_boost_resource_lists(self):
        self.assertIn("!ar.CanRead(count * sizeof(Item))", self.code)
        self.assertIn("read_list(buffers, NUM_BUFFERS)", self.code)
        self.assertIn("read_list(images, NUM_IMAGES * 4)", self.code)
        self.assertIn("read_list(samplers, NUM_SAMPLERS * 4)", self.code)
        self.assertIn("read_list(fmasks, NUM_FMASKS)", self.code)
        self.assertIn("!ar.CanRead(flat_size * sizeof(u32))", self.code)

    def test_keeps_background_warmup_and_private_mali_driver_cache(self):
        self.assertIn("return StartBackgroundWarmUp();", self.code)
        self.assertIn("warm.mali_worker_cache", self.code)


if __name__ == "__main__":
    unittest.main()
