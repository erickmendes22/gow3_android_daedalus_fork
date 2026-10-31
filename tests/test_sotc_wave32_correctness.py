#!/usr/bin/env python3
"""Do not turn off SotC's usable Adreno Wave32 path or log it too early."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "ports/sotc/android/stage_adreno_wave32.py"
RUN = ROOT / "ports/sotc/android/run-sotc-bionic.sh"
UI = ROOT / "android-launcher/app/src/main/java/com/gow3/android/ui/SotcScreen.kt"

class Wave32Policy(unittest.TestCase):
    def test_logging_after_vulkan_feature_initialization(self):
        script = STAGE.read_text()
        self.assertIn('vk13_features = feature_chain.get<vk::PhysicalDeviceVulkan13Features>();', script)
        self.assertIn('SotC Adreno Wave32 effective: %s', script)
        self.assertIn('compiler=%u, vertex=%u, fragment=%u, compute=%u, physical=%u', script)
        self.assertIn('UseAdrenoWave32() ? "active" : "inactive"', script)
        self.assertNotIn('SotC Adreno Wave32: %s (requested=', script)

    def test_wave32_shader_policy_preserved(self):
        script = STAGE.read_text()
        self.assertIn('if (UseAdrenoWave32()) return false;', script)
        self.assertIn('if (UseAdrenoWave32()) return 32u;', script)
        self.assertEqual(script.count('if (UseAdrenoWave32()) return 32u;'), 2)

    def test_user_toggle_and_cache_variants_remain(self):
        run = RUN.read_text()
        ui = UI.read_text()
        self.assertIn('SOTC_ADRENO_WAVE32:-0', run)
        self.assertIn('sotc_gpu_profile=wave32', run)
        self.assertIn('sotc_gpu_profile=wave64', run)
        self.assertIn('sotc_adreno_wave32', ui)
        self.assertIn('Adreno: compatibilidade Wave32', ui)

if __name__ == "__main__":
    unittest.main()
