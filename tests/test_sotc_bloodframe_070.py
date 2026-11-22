#!/usr/bin/env python3
"""SotC native 0.1.70: real Bloodframe output vs dummy launcher toggle."""
from pathlib import Path
import unittest
R=Path(__file__).resolve().parents[1]
def read(p):return (R/p).read_text()

class Bloodframe070(unittest.TestCase):
    def test_real_external_vulkan_output(self):
        s=read('ports/sotc/android/stage_sotc_bloodframe_070.py')
        for call in ('Lsfg::Create','ProcessFrame','PresentBloodframe','GetOutput','OutputSubmitted',
                     'VK_QUEUE_FAMILY_EXTERNAL','vk::ImageLayout::eTransferSrcOptimal',
                     'source_acquire','source_release'):
            self.assertIn(call,s)
        self.assertIn('cmdbuf.blitImage(generated',s)
        self.assertIn('if (n<0)',s)
        self.assertIn('lsfg.reset()',s)
        self.assertNotIn('FPS 60',s)
    def test_bloodframe_engine_source_and_exact_v2_abi(self):
        cpp=read('ports/sotc/android/bloodframe/vk_lsfg.cpp')
        header=read('ports/sotc/android/bloodframe/bb_lsfg.h')
        self.assertIn('gow3_vk_get_instance_proc_addr()',cpp)
        self.assertIn('bb_lsfg_init_v2',header)
        self.assertIn('bb_lsfg_present',header)
        self.assertIn('AHardwareBuffer',header)
        self.assertIn('bb_lsfg_present',cpp)
    def test_runtime_fail_closed_and_not_default(self):
        java=read('android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java')
        self.assertIn('BB_LSFG_MULTIPLIER',java)
        self.assertIn('BB_MAKO_MODEL',java)
        self.assertIn('BB_LSFG_LIB',java)
        self.assertIn('bloodframe ? "6" : "3"',java)
        self.assertIn('sotcFgActive',java)
        sh=read('ports/sotc/android/run-sotc-bionic.sh')
        self.assertIn('requested MAKO x2 but engine/model unavailable',sh)
        runtime=read('android-launcher/app/src/main/java/ro/cobrabm/fexdroid/RuntimeInstaller.java')
        self.assertIn('sotcport/arm64/lib/libbloodframe.so',runtime)
        self.assertIn('sotcport/mako-fg/model/weights.bin',runtime)
        screen=read('android-launcher/app/src/main/java/com/gow3/android/ui/SotcScreen.kt')
        self.assertIn('values["sotc_bloodframe_fg"]?:"off"',screen)
        self.assertIn('Bloodframe ×2',screen)
        self.assertIn('CC BY-NC 4.0',screen)
    def test_repack_requires_real_renderer_and_hash_verified_model(self):
        s=read('ports/sotc/android/inject_bloodframe_070.py')
        self.assertIn('bb_lsfg_present',s)
        self.assertIn('SOTC BLOODFRAME: ACTIVE',s)
        self.assertIn('EXPECTED_MODEL',s)
        self.assertIn('Unresolved internal C++ renderer symbols',s)
        self.assertIn('sotcport/arm64/lib/libbbgpu.so',s)
        self.assertIn('sotcport/arm64/lib/libbloodframe.so',s)
if __name__=='__main__':unittest.main()
