#!/usr/bin/env python3
"""SotC Android 0.1.47: independent nondeferred host staging reuse."""
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ports/sotc/android"))
from stage_sotc_host_large_pow2_047 import patch_host_large_pow2
from stage_sotc_pc072_staging_keep_046 import patch_staging

REL = "shadps4/video_core/renderer_vulkan/vk_staging_buffer_pool.cpp"


class HostLargeStaging(unittest.TestCase):
    def test_pinned_renderer_and_preserved_deferred_readback(self):
        upstream = ROOT / "upstream-sotc/gpu" / REL
        if not upstream.exists():
            self.skipTest("pinned PC source not checked out")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            target = out / REL
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(upstream, target)
            original = target.read_text()
            patch_staging(out)
            patch_host_large_pow2(out)
            patched = target.read_text()
            self.assertIn('std::getenv("SOTC_HOST_LARGE_POW2")', patched)
            self.assertIn('type != MemoryType::DeviceLocal && size <= 64_MB', patched)
            self.assertIn('!deferred &&', patched)
            self.assertIn('const u64 max_size = deferred ? alloc_size', patched)
            self.assertIn('host_pow2 ? alloc_size * 2', patched)
            self.assertEqual(original.count("scheduler.IsFree(entry.tick)"),
                             patched.count("scheduler.IsFree(entry.tick)"))
            self.assertEqual(original.count("best->held = deferred"),
                             patched.count("best->held = deferred"))
            self.assertIn('type == u32(MemoryType::DeviceLocal) ? 0 : keep_host_blocks', patched)
            self.assertNotIn('SOTC_STAGING_KEEP_VRAM_MB', patched)
            with self.assertRaisesRegex(RuntimeError, "source changed"):
                patch_host_large_pow2(out)

    def test_only_one_new_option_with_zero_default(self):
        screen = (ROOT / "android-launcher/app/src/main/java/com/gow3/android/ui/SotcScreen.kt").read_text()
        activity = (ROOT / "android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java").read_text()
        shell = (ROOT / "ports/sotc/android/run-sotc-bionic.sh").read_text()
        self.assertIn('(values["sotc_pc072_host_large_pow2"]?:"0")=="1"', screen)
        self.assertIn('"1".equals(setting("sotc_pc072_host_large_pow2"))', activity)
        self.assertIn('export SOTC_HOST_LARGE_POW2=${SOTC_HOST_LARGE_POW2:-0}', shell)
        self.assertIn('case "$SOTC_HOST_LARGE_POW2" in 0|1)', shell)
        for preserved in ("SOTC_POOL_OWNER", "SOTC_RB_HOT", "BB_READBACKS",
                          "SOTC_RB_STREAM", "SOTC_STAGING_KEEP_MB", "SOTC_MUTEX_SPIN_US"):
            self.assertIn(preserved, shell)
        self.assertIn('versionName = "0.1.47-host-large-pow2"',
                      (ROOT / "android-launcher/app/build.gradle.kts").read_text())


if __name__ == "__main__":
    unittest.main()
