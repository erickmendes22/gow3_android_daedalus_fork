#!/usr/bin/env python3
# SotC Adreno: the native extensions are absent; refuse to silently omit interpolation.
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
STAGE=ROOT/"ports/sotc/android/stage_adreno_barycentric_gs.py"
RENDER=ROOT/"ports/sotc/android/stage_renderer.py"
WAVE=ROOT/"ports/sotc/android/stage_adreno_wave32.py"
RUN=ROOT/"ports/sotc/android/run-sotc-bionic.sh"


class AdrenoBarycentricTest(unittest.TestCase):
    def test_upstream_fallback_is_enabled_only_when_vulkan_can_run_it(self):
        s=STAGE.read_text()
        self.assertIn("instance.GetVendorID() == 0x5143",s)
        self.assertIn("instance.IsGeometryStageSupported()",s)
        self.assertIn("!khr_barycentric && !amd_explicit_vertex",s)
        self.assertIn('!env_is("SOTC_BARYCENTRIC_GS", "0")',s)
        self.assertIn('instance.GetDriverID() == vk::DriverId::eNvidiaProprietary ||',s)
        self.assertIn("adreno_missing_barycentrics",s)
        self.assertIn("GS_fallback=%d",s)
        self.assertIn("#ifdef __ANDROID__",s)

    def test_proven_pipeline_and_interpolators_remain_used(self):
        s=STAGE.read_text()
        self.assertIn("GraphicsPipeline::SerializationSupport::with_gs = barycentric_via_gs;",s)
        self.assertIn(".supports_fragment_shader_barycentric = khr_barycentric || barycentric_via_gs,",s)
        self.assertIn(".barycentric_via_gs = barycentric_via_gs,",s)
        self.assertIn("from stage_adreno_barycentric_gs import patch_adreno_barycentric_gs",RENDER.read_text())

    def test_wave32_stage_guard(self):
        s=WAVE.read_text()
        self.assertIn("requiredSubgroupSizeStages & stage",s)
        self.assertEqual(s.count('if (UseAdrenoWave32()) return 32u;'),1)
        self.assertIn('return u32(vk13_props.requiredSubgroupSizeStages & stage) != 0 ? 32u : 0u;',s)

    def test_no_stale_barycentric_shader_cache_and_no_wave_regression(self):
        s=RUN.read_text()
        self.assertIn("gpu-user-srt-phi7-tess-gs-position-turnip-nomultipos-",s)
        self.assertIn("profile=$sotc_gpu_profile",s)
        self.assertIn("export BB_READBACKS=2",s)
        self.assertIn("export SOTC_RB_ASYNC=0",s)
        self.assertNotIn("export SOTC_ADRENO_WAVE32=0",s)

if __name__ == "__main__":
    unittest.main()
