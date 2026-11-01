#!/usr/bin/env python3
"""Regression test: FAST_BIND must not omit per-draw Vulkan resource tracking."""
import unittest
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]


class ResourceCoherenceTest(unittest.TestCase):
    def test_staging_uses_android_resource_guard(self):
        src = (ROOT / "ports/sotc/android/stage_renderer.py").read_text()
        self.assertIn("from stage_resource_coherence import patch_resource_coherence", src)
        self.assertIn("patch_resource_coherence(out)", src)

    def test_source_patch_only_changes_fastbind_eligibility(self):
        import sys
        sys.path.insert(0, str(ROOT / "ports/sotc/android"))
        from stage_resource_coherence import patch_resource_coherence

        source = """bool Rasterizer::FastBindEligible(const Pipeline* pipeline) const {
    for (const auto* stage : pipeline->GetStages()) {
        if (stage->has_storage_images || !stage->fmasks.empty()) {
            return false;
        }
    }
    return true;
}
u64 Rasterizer::FastBindHash(const Pipeline* pipeline, const Shader::PushData& push_data) const {return 1;}
bool Rasterizer::BindResources(const Pipeline* pipeline) {
    if (fast_bind_hit) return true;
    fast_bind_hit = true;
    BindTextures(*stage, binding);
    BindBuffers(*stage, binding, push_data);
    return true;
}
void Rasterizer::ResetBindings(bool is_compute) {
    bound_images.clear();
    bound_buffers.clear();
}
"""
        with tempfile.TemporaryDirectory() as d:
            gpu = Path(d)
            file = gpu / "shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp"
            file.parent.mkdir(parents=True)
            file.write_text(source)
            patch_resource_coherence(gpu)
            out = file.read_text()
            a = out.index("bool Rasterizer::FastBindEligible(")
            b = out.index("u64 Rasterizer::FastBindHash(", a)
            gate = out[a:b]
            self.assertIn("#ifdef __ANDROID__", gate)
            self.assertIn("!stage->images.empty()", gate)
            self.assertIn("!stage->buffers.empty()", gate)
            self.assertIn("!stage->samplers.empty()", gate)
            self.assertIn("!stage->fmasks.empty()", gate)
            self.assertIn("#endif", gate)
            self.assertIn("fast_bind_hit = true;", out)
            self.assertIn("bound_images.clear();", out)
            self.assertIn("bound_buffers.clear();", out)
            self.assertIn("BindTextures(*stage, binding);", out)
            self.assertIn("BindBuffers(*stage, binding, push_data);", out)
            self.assertEqual(out.count("bool Rasterizer::FastBindEligible("), 1)

    def test_fail_closed_on_drift(self):
        import sys
        sys.path.insert(0, str(ROOT / "ports/sotc/android"))
        from stage_resource_coherence import patch_resource_coherence
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp"
            path.parent.mkdir(parents=True)
            path.write_text("bool Rasterizer::FastBindEligible() {}")
            with self.assertRaises(ValueError):
                patch_resource_coherence(Path(d))


if __name__ == "__main__":
    unittest.main()
