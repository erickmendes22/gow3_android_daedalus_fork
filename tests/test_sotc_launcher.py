#!/usr/bin/env python3
from pathlib import Path
import unittest
SCRIPT=Path(__file__).resolve().parents[1]/'ports/sotc/android/run-sotc-bionic.sh'
class SotcLauncherTest(unittest.TestCase):
    def test_sotc_files_and_not_gow3_prepare(self):
        s=SCRIPT.read_text()
        for needle in ('sotc_prepare_game.py','boot-linked.bin','content.bin','sotc-cpu.bin','--sotc-cmdline','libbbgpu.so','SOTC_PRESENT_SOCKET','GOW3_VULKAN_DRIVER'):
            self.assertIn(needle,s)
        self.assertNotIn('"$runtime/bin/gow3-prepare"',s)

    def test_gpu_cache_profiles_do_not_reuse_old_shaders(self):
        s = SCRIPT.read_text()
        self.assertIn('gpu-user-srt-phi7-tess-gs-position-turnip-nomultipos-$sotc_gpu_profile', s)
        self.assertIn('1) sotc_gpu_profile=wave32', s)
        self.assertIn('*) sotc_gpu_profile=wave64', s)
        self.assertIn('--user "$base/user"', s)
        self.assertNotIn('gpu-user-wave32"', s)
        activity = (Path(__file__).resolve().parents[1] / 'android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java').read_text()
        self.assertIn('"1".equals(setting("sotc_adreno_wave32")) ? "1" : "0"', activity)

if __name__=='__main__': unittest.main()
