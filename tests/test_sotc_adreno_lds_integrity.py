#!/usr/bin/env python3
"""Adreno Wave64 must retain SotC LDS barriers; Wave32 already had them."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ports/sotc/android"))
from stage_adreno_lds_integrity import patch_adreno_lds_integrity

TARGET = "shadps4/video_core/renderer_vulkan/vk_pipeline_cache.cpp"


class AdrenoLdsIntegrity(unittest.TestCase):
    def test_pinned_shader_profile_repaired_and_idempotent(self):
        upstream = ROOT / "upstream-sotc/gpu" / TARGET
        if not upstream.is_file():
            self.skipTest("Pinned SotC GPU sources not checked out")
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / TARGET
            target.parent.mkdir(parents=True, exist_ok=True)
            original = upstream.read_text()
            self.assertIn("instance.SubgroupSize() < 64 || amd64_lds,", original)
            target.write_text(original)
            patch_adreno_lds_integrity(Path(temp))
            result = target.read_text()
            self.assertIn("instance.SubgroupSize() < 64 || amd64_lds ||", result)
            self.assertIn("instance.GetVendorID() == 0x5143,", result)
            self.assertIn("instance.GetDriverID() == vk::DriverId::eNvidiaProprietary", result)
            self.assertIn("instance.GetDriverID() == vk::DriverId::eMesaKosmickrisp", result)
            with self.assertRaises(ValueError):
                patch_adreno_lds_integrity(Path(temp))

    def test_staging_and_clean_cache(self):
        stage = (ROOT / "ports/sotc/android/stage_renderer.py").read_text()
        runner = (ROOT / "ports/sotc/android/run-sotc-bionic.sh").read_text()
        self.assertIn("from stage_adreno_lds_integrity import patch_adreno_lds_integrity", stage)
        self.assertIn("patch_adreno_lds_integrity(out)", stage)
        self.assertIn('gpu-user-srt-phi7-tess-gs-position-turnip-nomultipos-$sotc_gpu_profile/lds-meta1', runner)
        self.assertIn("sotc_gpu_profile=wave32", runner)
        self.assertIn("sotc_gpu_profile=wave64", runner)


if __name__ == "__main__":
    unittest.main()
