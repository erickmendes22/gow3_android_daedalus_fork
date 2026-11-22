#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Conservative ARM64 indirect zero-count fastpath invariants and launcher controls."""
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ports/sotc/android"))
from stage_sotc_indirect_empty_bind_063 import patch

class IndirectEmptyBindTests(unittest.TestCase):
    def make_renderer(self, root: Path, broken=False):
        p = root / "shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp"
        p.parent.mkdir(parents=True)
        p.write_text("""
void Rasterizer::DrawIndirect(bool is_indexed, VAddr arg_address, u32 offset, u32 stride,
                              u32 max_count, VAddr count_address, u16 vertex_sgpr_offset,
                              u16 instance_sgpr_offset, const Pipeline* resolved,
                              bool use_resolved) {
    PrepareRenderState(pipeline);
    if (!BindResources(pipeline)) {
    }
    const auto state = BeginRendering(pipeline);
    RefreshImageLayouts();
    ResetBindings(false);
    FlushPeriodic();
    scheduler.BeginRendering(state);
    if (direct_args && count_address == 0 && max_count == 1 &&
        buffer_cache.IsRegionGpuModified(arg_address + offset, stride)) {
    }
}
"""+ ("" if broken else "// sotc: the two grass compute shaders\n"))
        return p

    def test_guards_and_renderpass_clear(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            p = self.make_renderer(root)
            patch(root)
            s = p.read_text()
            self.assertEqual(s.count("SOTC INDIRECT EMPTY BIND:"),1)
            self.assertIn('std::getenv("SOTC_INDIRECT_EMPTY_BIND")',s)
            self.assertIn("if (!single || Dlssg::CapturingInputs())",s)
            self.assertIn("buffer_cache.IsRegionGpuModified(args_addr, stride)",s)
            self.assertIn("count_address == 0 && max_count == 1",s)
            self.assertIn("counts[0] == 0 || counts[1] == 0",s)
            self.assertIn("const auto state = BeginRendering(pipeline);",s)
            self.assertIn("scheduler.BeginRendering(state);",s)
            self.assertIn("RefreshImageLayouts();",s)
            self.assertIn("if (needs_barrier) runtime.FlushBarriers();",s)
            self.assertIn("ResetBindings(false);",s)
            self.assertIn("FlushPeriodic();",s)
            self.assertIn("++zero;",s)
            self.assertIn("multi_or_count=",s)
            with self.assertRaises(RuntimeError):
                patch(root)

    def test_missing_required_anchor_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            self.make_renderer(root,broken=True)
            with self.assertRaises(RuntimeError):
                patch(root)

    def test_ui_reversible_and_launcher_preserves_value(self):
        activity=(ROOT/"android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java").read_text()
        ui=(ROOT/"android-launcher/app/src/main/java/com/gow3/android/ui/SotcScreen.kt").read_text()
        self.assertIn('env.put("SOTC_INDIRECT_EMPTY_BIND",',activity)
        self.assertIn('"1".equals(setting("sotc_indirect_empty_bind_063"))',activity)
        self.assertIn('values["sotc_indirect_empty_bind_063"]?:"0"',ui)
        self.assertIn('SOTC INDIRECT EMPTY BIND',ui)

if __name__ == "__main__":
    unittest.main()
