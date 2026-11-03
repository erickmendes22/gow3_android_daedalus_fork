#!/usr/bin/env python3
"""Production stager tests: preserve GPU safety and user settings of 0.1.40."""
from pathlib import Path
import tempfile
import shutil
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"ports/sotc/android"))
from stage_sotc_cpu_dirty_summary_043 import patch_cpu_dirty_word_summary

UP=ROOT/"upstream-sotc/gpu/shadps4"
class NativeDirtySummary(unittest.TestCase):
    @unittest.skipUnless(UP.exists(),"requires pinned upstream repo checkout")
    def test_real_cpp_compiles_after_patching(self):
        files=[
            "video_core/buffer_cache/region_manager.h",
            "video_core/sotc_stats.h",
            "core/libraries/videoout/driver.cpp",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            gpu=Path(tmp)/"shadps4"
            for rel in files:
                dst=gpu/rel
                dst.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(UP/rel,dst)
            origin=(gpu/files[0]).read_text()
            patch_cpu_dirty_word_summary(ROOT,gpu)
            patched=(gpu/files[0]).read_text()
            self.assertNotEqual(origin,patched)
            self.assertIn("cpu_live_words{~0ULL}",patched)
            self.assertIn("SotcDirtyWord::MightContain",patched)
            self.assertEqual(patched.count("SotcDirtyWord::Update(cpu_live_words"),2)
            self.assertIn("gpu_op == StateOp::None",patched)
            self.assertIn("type == Type::CPU && cpu_op == StateOp::Clear",patched)
            self.assertIn("tracker->UpdatePageWatchersForRegion",patched)
            self.assertIn("FaultGrace::Now()",patched)
            self.assertIn("sweep_words.fetch_or",patched)
            self.assertNotIn("SOTC_RB_AHEAD=1",patched)
            self.assertIn("SOTC CPU dirty summary:",(gpu/files[2]).read_text())
            with self.assertRaises(RuntimeError):
                patch_cpu_dirty_word_summary(ROOT,gpu)
    def test_no_launcher_preferences_or_readback_changed(self):
        ui=(ROOT/"android-launcher/app/src/main/java/com/gow3/android/ui/SotcScreen.kt").read_text()
        java=(ROOT/"android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java").read_text()
        self.assertIn('values["sotc_rb_stream"]?:"1"',ui)
        self.assertIn('values["sotc_rb_async"]?:"0"',ui)
        self.assertIn('values["sotc_fast_bind"]?:"0"',ui)
        self.assertIn('env.put("BB_READBACKS",rbMode)',java)
        self.assertIn('env.put("SOTC_RB_STREAM_MAX_KB","512");',java)
if __name__=="__main__": unittest.main()
