#!/usr/bin/env python3
"""PC 0.71/0.72 Android port regression, pinned stable 0.1.40 UI/runtime."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
def read(p): return (ROOT/p).read_text()
class Pc072Android(unittest.TestCase):
    def test_release_only_filters_verified_fex_guest_callsite(self):
        runtime=read("src/runtime_memory.c")
        probe=read("src/probe.c")
        self.assertIn('guest_cpu_return_address((uintptr_t)__builtin_return_address(0))==sotc_pool_release_site',runtime)
        self.assertIn('info->flags &= ~16u;',runtime)
        self.assertIn('sotc_pool_owner[physical>>16]',runtime)
        self.assertIn('if (right.kind!=KIND_RESERVED) right.phys+=a-vmas[i].start;',runtime)
        self.assertIn('if (kind==KIND_DIRECT) sotc_owner_note(phys,address,size);',runtime)
        self.assertIn('const int recognized=size>0x1ac82 && image[0x1ac7d]==0xe8;',probe)
        self.assertIn('runtime_memory_set_release_site((uintptr_t)(image+0x1ac82));',probe)
        self.assertIn('setenv("SOTC_RB_HOT","0",1);',probe)
    def test_experimental_enabled_only_with_precise_readback(self):
        script=read("ports/sotc/android/run-sotc-bionic.sh")
        java=read("android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java")
        screen=read("android-launcher/app/src/main/java/com/gow3/android/ui/SotcScreen.kt")
        self.assertIn('export SOTC_POOL_OWNER=${SOTC_POOL_OWNER:-1}',script)
        self.assertIn('export SOTC_RB_HOT=${SOTC_RB_HOT:-0}',script)
        self.assertIn('if [ "$SOTC_POOL_OWNER" != 1 ] || [ "$BB_READBACKS" != 2 ]; then SOTC_RB_HOT=0;',script)
        self.assertIn('env.put("SOTC_POOL_OWNER","1");',java)
        self.assertIn('env.put("SOTC_RB_HOT",',java)
        self.assertIn('"1".equals(setting("sotc_pc072_fast_readbacks"))',java)
        self.assertIn('(values["sotc_pc072_fast_readbacks"]?:"0")=="1"',screen)
        self.assertIn('values["sotc_readbacks"]?:"2"',screen)
        self.assertIn('values["sotc_vsync"]?:',screen)
    def test_renderer_no_unsafe_changes(self):
        script=read("ports/sotc/android/run-sotc-bionic.sh")
        stage=read("ports/sotc/android/stage_renderer.py")
        self.assertIn('export SOTC_UPLOAD_BUDGET_MB=0',script)
        self.assertIn('export SOTC_LOD_LEVEL=${SOTC_LOD_LEVEL:-2}',script)
        self.assertIn('export SOTC_LOD_POOL_LOW=${SOTC_LOD_POOL_LOW:-8}',script)
        self.assertNotIn('SOTC_STAGING_LARGE_POW2',stage)
        self.assertNotIn('SotcReadback::CoalesceAdjacent',stage)
        self.assertNotIn('SotcDirtyWord::Update',stage)
        self.assertNotIn('SotcInflight::Overlaps',stage)
    def test_runtime_and_ui_version_agree(self):
        self.assertIn("version='0.1.45-boot-test'",read("ports/sotc/android/package_sotc_runtime.py"))
        self.assertIn('0.1.45-pc072-pool-owner-fast-readbacks',read("ports/sotc/android/sign_sotc_apk.sh"))
        self.assertIn('versionCode = 10046',read("android-launcher/app/build.gradle.kts"))
if __name__=="__main__":unittest.main()
