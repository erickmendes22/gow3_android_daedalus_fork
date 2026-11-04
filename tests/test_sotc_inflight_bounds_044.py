#!/usr/bin/env python3
"""End-to-end staging checks against pinned 0.1.40 GPU renderer source."""
from pathlib import Path
import shutil, tempfile, sys, unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"ports/sotc/android"))
from stage_sotc_inflight_bounds_044 import patch_inflight
SOURCE=ROOT/"upstream-sotc/gpu/shadps4"
class ReadbackBounds(unittest.TestCase):
    @unittest.skipUnless(SOURCE.exists(),"pinned upstream checkout unavailable")
    def test_exact_original_gpu_src_and_guest_safety(self):
        with tempfile.TemporaryDirectory() as td:
            gpu=Path(td)
            files=[
                "video_core/buffer_cache/buffer_cache.cpp",
                "video_core/buffer_cache/buffer_cache.h",
                "video_core/sotc_stats.h",
                "core/libraries/videoout/driver.cpp",
            ]
            for rel in files:
                dst=gpu/"shadps4"/rel
                dst.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(SOURCE/rel,dst)
            original=(gpu/"shadps4"/files[0]).read_text()
            patch_inflight(ROOT,gpu)
            actual=(gpu/"shadps4"/files[0]).read_text()
            self.assertNotEqual(original,actual)
            self.assertEqual(actual.count("SotcInflight::Overlaps"),3)
            self.assertIn("readback.inflight_lo = ~VAddr{0};",actual)
            self.assertIn("readback.inflight_hi = 0;",actual)
            self.assertIn("readback.inflight_lo = std::min",actual)
            self.assertIn("readback.inflight_hi = std::max",actual)
            for safety in ("scheduler.WaitSubmitted(readback.tick, false);",
                           "scheduler.GetWorkSemaphore()->Wait(readback.tick);",
                           "FinishAsyncReadback(readback);",
                           "ApplyDownloads(readback.pending, download.mapped, download.offset);",
                           "SubtractDownloaded(readback.pending);",
                           "MarkWrittenByGuest(readback.device_addr, readback.size);"):
                self.assertIn(safety,actual)
            self.assertIn("SOTC inflight bounds:",(gpu/"shadps4"/files[3]).read_text())
            with self.assertRaises(RuntimeError):
                patch_inflight(ROOT,gpu)
    def test_baseline_ui_and_readback_settings_intact(self):
        ui=(ROOT/"android-launcher/app/src/main/java/com/gow3/android/ui/SotcScreen.kt").read_text()
        java=(ROOT/"android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java").read_text()
        self.assertIn('values["sotc_rb_async"]?:"0"',ui)
        self.assertIn('values["sotc_fast_bind"]?:"0"',ui)
        self.assertIn('env.put("BB_READBACKS",rbMode)',java)
        self.assertIn('env.put("SOTC_RB_STREAM_MAX_KB","512");',java)
if __name__=="__main__":unittest.main()
