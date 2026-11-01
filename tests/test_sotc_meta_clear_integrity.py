#!/usr/bin/env python3
"""Regression: one metadata clear cannot swallow another compute output."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ports/sotc/android"))
from stage_meta_clear_integrity import patch_meta_clear_integrity

RASTER = "shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp"


class MetaClearIntegrity(unittest.TestCase):
    def test_guard_modifies_real_upstream_renderer(self):
        source = ROOT / "upstream-sotc/gpu" / RASTER
        if not source.exists():
            self.skipTest("Pinned SotC upstream not checked out")
        original = source.read_text()
        self.assertIn("bool Rasterizer::IsComputeMetaClear", original)
        self.assertIn("texture_cache.ClearMeta(address)", original)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / RASTER
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(original)
            patch_meta_clear_integrity(Path(temp))
            result = path.read_text()
            self.assertIn("bool metadata_only_dispatch = info.images.empty();", result)
            self.assertIn("if (desc.IsSpecial() || ++non_special_writes > 1)", result)
            self.assertIn("metadata_only_dispatch &= non_special_writes == 1;", result)
            self.assertIn("!info.has_bitwise_xor && metadata_only_dispatch", result)
            self.assertIn("texture_cache.ClearMeta(address)", result)
            self.assertIn("constexpr bool metadata_only_dispatch = true;", result)
            self.assertNotIn("if (!info.has_bitwise_xor) {", result)
            # Native shader and resource binding logic is unchanged.
            self.assertEqual(result.count("void Rasterizer::DispatchDirect("),
                             original.count("void Rasterizer::DispatchDirect("))
            self.assertEqual(result.count("bool Rasterizer::BindResources("),
                             original.count("bool Rasterizer::BindResources("))
            with self.assertRaises(ValueError):
                patch_meta_clear_integrity(Path(temp))

    def test_build_stages_the_guard_without_changing_driver_modes(self):
        renderer = (ROOT / "ports/sotc/android/stage_renderer.py").read_text()
        runner = (ROOT / "ports/sotc/android/run-sotc-bionic.sh").read_text()
        self.assertIn("from stage_meta_clear_integrity import patch_meta_clear_integrity", renderer)
        self.assertIn("patch_meta_clear_integrity(out)", renderer)
        for important in ("export BB_READBACKS=2", "export SOTC_RB_ASYNC=${SOTC_RB_ASYNC:-0}",
                          "export SOTC_UPLOAD_BUDGET_MB=0",
                          "export SOTC_ASYNC_SHADERS=${SOTC_ASYNC_SHADERS:-0}"):
            self.assertIn(important, runner)

    def test_no_unrelated_auto_fog_capture(self):
        runner = (ROOT / "ports/sotc/android/run-sotc-bionic.sh").read_text()
        self.assertNotIn("export SOTC_AUTO_GPU_DUMP_AFTER=80", runner)
        self.assertNotIn("export SOTC_DUMP=b33e9db6", runner)


if __name__ == "__main__":
    unittest.main()
