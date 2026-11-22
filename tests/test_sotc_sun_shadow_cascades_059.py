#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Guard the only two direct/indirect sun-cascade benchmark draw entrypoints."""
from pathlib import Path
import tempfile
import unittest
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ports/sotc/android"))
from stage_sotc_sun_shadow_cascades_059 import patch


class SunCascadeTests(unittest.TestCase):
    def mock(self, base: Path) -> None:
        renderer = base / "shadps4/video_core/renderer_vulkan"
        renderer.mkdir(parents=True)
        (renderer / "vk_rasterizer.h").write_text("    bool ReuseShadowCascade();\n")
        (renderer / "vk_rasterizer.cpp").write_text(
            "// sotc: TakeHudless (vk_rasterizer.h).\n"
            "    if (SkipStaggeredShadow(liverpool->DrawRegs()) || ReuseShadowCascade()) {\n"
            "        return;\n    }\n"
            "    if (SkipStaggeredShadow(liverpool->DrawRegs()) || ReuseShadowCascade()) {\n"
            "        return;\n    }\n"
            "texture_cache.FindImage(desc);\n"
            "texture_cache.FindRenderTarget(image_id, desc);\n"
            "VideoCore::MarkGpuModified(image);\n"
            "SotcStats::flip_count.load(std::memory_order_relaxed);\n"
            "regs.depth_clear;\n")

    def test_patched_draw_only_and_safe_depth_clear(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self.mock(base)
            patch(base)
            gpu = (base / "shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text()
            self.assertEqual(gpu.count("if (SkipSunShadowBenchmark() ||"), 2)
            self.assertIn('std::getenv("SOTC_SUN_CASCADES")', gpu)
            self.assertIn("if (keep >= 5) return false;", gpu)
            self.assertIn("regs.depth_buffer.Pitch() != regs.depth_buffer.Height()", gpu)
            self.assertIn("complete_maps == 1 ? winner : 0", gpu)
            self.assertIn("(mask & 0x1fu) == 0x1fu", gpu)
            self.assertIn("AmdGpu::ColorControl::OperationMode::Disable", gpu)
            self.assertIn("candidates[addr] |= (1u << first);", gpu)
            self.assertIn("first < keep", gpu)
            self.assertIn("image.info.resources.layers <= first", gpu)
            self.assertIn("first != last", gpu)
            self.assertIn("vk::ImageLayout::eTransferDstOptimal", gpu)
            self.assertIn("clearDepthStencilImage(", gpu)
            self.assertIn("vk::ClearDepthStencilValue{regs.depth_clear, 0}", gpu)
            self.assertIn("return false; // never skip unless the no-shadow depth clear is possible", gpu)
            self.assertIn("VideoCore::MarkGpuModified(image)", gpu)
            self.assertIn("SOTC SUN CASCADES:", gpu)
            self.assertIn("bool SkipSunShadowBenchmark();",
                          (base / "shadps4/video_core/renderer_vulkan/vk_rasterizer.h").read_text())
            with self.assertRaises(ValueError):
                patch(base)

    def test_missing_draw_guard_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self.mock(base)
            target = base / "shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp"
            target.write_text(target.read_text().replace(
                "    if (SkipStaggeredShadow(liverpool->DrawRegs()) || ReuseShadowCascade()) {",
                "// removed"))
            with self.assertRaises(ValueError):
                patch(base)

    def test_launcher_has_reversible_modes(self):
        activity = (ROOT / "android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java").read_text()
        ui = (ROOT / "android-launcher/app/src/main/java/com/gow3/android/ui/SotcScreen.kt").read_text()
        launcher = (ROOT / "ports/sotc/android/run-sotc-bionic.sh").read_text()
        for option in ("0", "1", "2", "3", "5"):
            self.assertIn(f'"{option}"', ui)
        self.assertIn('env.put("SOTC_SUN_CASCADES",', activity)
        self.assertIn('export SOTC_SUN_CASCADES=', launcher)
        self.assertIn('SOTC_SUN_CASCADES=', launcher)

if __name__ == "__main__":
    unittest.main()
