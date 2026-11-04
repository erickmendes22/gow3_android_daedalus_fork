#!/usr/bin/env python3
"""PC 0.71/0.72 SotC Android experiments: source and UI/runtime regression."""
from pathlib import Path
import tempfile, shutil, sys, unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"ports/sotc/android"))
from stage_sotc_pc072_staging_keep_046 import patch_staging
class PcMutexStage(unittest.TestCase):
    def test_stage_exact_pinned_renderer_and_low_vram_guards(self):
        rel="shadps4/video_core/renderer_vulkan/vk_staging_buffer_pool.cpp"
        source=ROOT/"upstream-sotc/gpu"/rel
        if not source.exists(): self.skipTest("pinned GPU source not checked out")
        with tempfile.TemporaryDirectory() as td:
            staged=Path(td); dst=staged/rel
            dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dst)
            old=dst.read_text()
            patch_staging(staged)
            text=dst.read_text()
            self.assertIn('std::min<u64>(v ? std::strtoull(v, nullptr, 10) : 0ull, 64ull)',text)
            self.assertIn('type == u32(MemoryType::DeviceLocal) ? 0 : keep_host_blocks',text)
            self.assertIn('frame > 60 && keep && ring.blocks.size() < keep',text)
            self.assertIn('std::make_unique<VideoCore::StreamBuffer>',text)
            self.assertIn('SOTC staging prewarm:',text)
            self.assertEqual(text.count('SOTC_STAGING_LARGE_POW2'),old.count('SOTC_STAGING_LARGE_POW2'))
            self.assertNotIn('SOTC_STAGING_KEEP_VRAM_MB',text)
            with self.assertRaisesRegex(RuntimeError,"source changed"):
                patch_staging(staged)
    def test_old_features_and_two_new_off_by_default(self):
        screen=(ROOT/"android-launcher/app/src/main/java/com/gow3/android/ui/SotcScreen.kt").read_text()
        activity=(ROOT/"android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java").read_text()
        shell=(ROOT/"ports/sotc/android/run-sotc-bionic.sh").read_text()
        for key in ("sotc_pc071_mutex_spin","sotc_pc072_staging_prewarm"):
            self.assertIn(f'(values["{key}"]?:"0")=="1"',screen)
            self.assertIn(f'"1".equals(setting("{key}"))',activity)
        self.assertIn('env.put("SOTC_MUTEX_SPIN_US",',activity)
        self.assertIn('env.put("SOTC_STAGING_KEEP_MB",',activity)
        self.assertIn('export SOTC_MUTEX_SPIN_US=${SOTC_MUTEX_SPIN_US:-0}',shell)
        self.assertIn('export SOTC_STAGING_KEEP_MB=${SOTC_STAGING_KEEP_MB:-0}',shell)
        for old in ("SOTC_POOL_OWNER","SOTC_RB_HOT","BB_READBACKS","SOTC_RB_STREAM"):
            self.assertIn(old,shell)
        self.assertIn('versionName = "0.1.46-pc072-mutex-stage"',(ROOT/"android-launcher/app/build.gradle.kts").read_text())
        self.assertIn("version='0.1.46-boot-test'",(ROOT/"ports/sotc/android/package_sotc_runtime.py").read_text())
    def test_mutex_bounded_and_reversible(self):
        s=(ROOT/"src/runtime_mutex.c").read_text()
        self.assertIn('getenv("SOTC_MUTEX_SPIN_US")',s)
        self.assertIn('if(n>100) n=100;',s)
        self.assertIn('sotc_spin_guest_mutex',s)
        self.assertIn('if(!spin_us)',s)
        self.assertIn('native=pthread_mutex_lock(&(*mutex)->native);',s)
        self.assertIn('if(native==EBUSY) native=pthread_mutex_lock(&(*mutex)->native);',s)
if __name__=="__main__":unittest.main()
