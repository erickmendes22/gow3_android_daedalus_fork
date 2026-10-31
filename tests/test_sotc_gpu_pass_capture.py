#!/usr/bin/env python3
"""Verify that Android GPU-stage readback is reachable, bounded and exportable.

Crucially this validates an actual patch of the pinned PC core sources, not
only string matches against the staging script. It adds no shader workaround.
"""
import sys
import tempfile
import unittest
from pathlib import Path
from shutil import copy2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ports/sotc/android"))
from stage_gpu_pass_capture import stage_pass_capture

SHIM = "shim/bbgpu.cpp"
RASTER = "shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp"


class GpuPassCapture(unittest.TestCase):
    def test_real_pinned_upstream_patch_idempotence_and_bounds(self):
        upstream = ROOT / "upstream-sotc/gpu"
        if not (upstream / SHIM).is_file() or not (upstream / RASTER).is_file():
            self.skipTest("Pinned upstream tree not checked out")
        with tempfile.TemporaryDirectory() as temp:
            gpu = Path(temp)
            for name in (SHIM, RASTER):
                target = gpu / name
                target.parent.mkdir(parents=True, exist_ok=True)
                copy2(upstream / name, target)
            original_shim = (gpu / SHIM).read_text()
            original_raster = (gpu / RASTER).read_text()
            self.assertIn("ConsumeImageDumpRequest() { return false; }", original_shim)
            self.assertIn("void Rasterizer::MaybeDumpImages(u64 pgm_hash)", original_raster)
            stage_pass_capture(gpu)
            shim = (gpu / SHIM).read_text()
            raster = (gpu / RASTER).read_text()
            self.assertIn("SOTC GPU PASS CAPTURE armed", shim)
            self.assertNotIn("ConsumeImageDumpRequest() { return false; }", shim)
            self.assertIn("SOTC_AUTO_GPU_DUMP_AFTER", shim)
            self.assertIn("SOTC_GPU_DUMP_DIR", raster)
            self.assertIn("SOTC GPU PASS CAPTURE image shader=", raster)
            self.assertIn("bytes <= 16_MB && total_bytes + bytes <= 64_MB", raster)
            self.assertIn("!info.props.is_depth", raster)
            self.assertIn("texture_cache.DumpImage(image_id,", raster)
            self.assertIn("if (pending.empty())", raster)
            self.assertIn("SOTC GPU PASS CAPTURE all requested compute stages visited", raster)
            # Shader execution and staging-copy sequencing must be unchanged.
            for line in ("cmdbuf.dispatch(cs_program.dim_x, cs_program.dim_y, cs_program.dim_z);",
                         "MaybeDumpImages(cs.pgm_hash);",
                         "ResetBindings(true);", "runtime.DownloadImage("):
                if line in original_raster:
                    self.assertIn(line, raster)
            with self.assertRaises(ValueError):
                stage_pass_capture(gpu)

    def test_runner_preserves_manual_bounded_capture_export(self):
        runner = (ROOT / "ports/sotc/android/run-sotc-bionic.sh").read_text()
        self.assertNotIn("export SOTC_DUMP=", runner)
        self.assertNotIn("export SOTC_AUTO_GPU_DUMP_AFTER=", runner)
        self.assertIn('export SOTC_GPU_DUMP_DIR="$base/logs/gpu_capture"', runner)
        self.assertNotIn("export SOTC_PASS_TRACE=1", runner)
        self.assertIn("GPU pass dumps remain available on demand", runner)
        stage = (ROOT / "ports/sotc/android/stage_renderer.py").read_text()
        self.assertIn("stage_pass_capture(out)", stage)
        java = (ROOT / "android-launcher/app/src/main/java/com/gow3/android/data/LogManager.kt").read_text()
        self.assertIn('"${SotcPaths.baseName(activity)}/logs"', java)
        archive = (ROOT / "android-launcher/app/src/main/java/com/gow3/android/data/LogArchive.kt").read_text()
        self.assertIn("logs.walkTopDown()", archive)


if __name__ == "__main__":
    unittest.main()
