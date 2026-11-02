#!/usr/bin/env python3
"""Prove the simplified 0.1.36 frontend does not force any 0.1.35 flags."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
UI=(ROOT/"android-launcher/app/src/main/java/com/gow3/android/ui/SotcScreen.kt").read_text()
JAVA=(ROOT/"android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java").read_text()
SH=(ROOT/"ports/sotc/android/run-sotc-bionic.sh").read_text()
INI=(ROOT/"ports/sotc/android/package_sotc_runtime.py").read_text()
GRADLE=(ROOT/"android-launcher/app/build.gradle.kts").read_text()

class StableSimple(unittest.TestCase):
    def test_stable_default_is_unmodified_native_environment(self):
        self.assertIn('values["sotc_perf_mode"]?:"stable"',UI)
        self.assertIn('"stable" to',UI)
        self.assertIn('"ahead" to',UI)
        self.assertIn('"submit" to',UI)
        self.assertIn('String perfMode=setting("sotc_perf_mode");',JAVA)
        self.assertIn('if ("ahead".equals(perfMode)) {',JAVA)
        self.assertIn('env.put("SOTC_RB_AHEAD","1");',JAVA)
        self.assertIn('} else if ("submit".equals(perfMode)) {',JAVA)
        self.assertIn('env.put("SOTC_FLUSH_US","1000");',JAVA)
        self.assertNotIn('env.put("SOTC_FLUSH_EVERY"',JAVA)
        self.assertNotIn('env.put("SOTC_FLUSH_US","0");',JAVA)
        self.assertNotIn('SOTC_FLUSH_EVERY',SH)
        self.assertNotIn('SOTC_RB_AHEAD=',SH)
        self.assertIn('sotc_readbacks=2',INI)
        self.assertIn('sotc_rb_stream=1',INI)
        self.assertIn('sotc_vm_range_cache=1',INI)
        self.assertIn('0.1.36-stable-simple',GRADLE)
    def test_advanced_collapsed_and_experimental_flags_not_forced(self):
        self.assertIn('advancedOptionsVisible by remember { mutableStateOf(false) }',UI)
        self.assertIn('if (advancedOptionsVisible) {',UI)
        self.assertIn('Mostrar opções técnicas avançadas',UI)
        self.assertNotIn('LABORATÓRIO DE DESEMPENHO',UI)
        for flag in ('SOTC_RB_NARROW','SOTC_DMA_MERGE','SOTC_PIPE_MEMO',
                     'SOTC_SHADOW_STAGGER','SOTC_COPY_BATCH','SOTC_FLUSH_EVERY'):
            self.assertNotIn('env.put("'+flag+'"',JAVA)
            self.assertNotIn('export '+flag+'=',SH)

if __name__=="__main__":
    unittest.main()
