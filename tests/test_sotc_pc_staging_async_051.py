#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""PC upstream streaming gains backported with verifiable safety invariants."""
import sys
import tempfile
import shutil
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"ports/sotc/android"))
from stage_sotc_pc_streaming_051 import patch_pc_streaming
UPSTREAM=ROOT/"upstream-sotc/gpu"
GPU_FILES=(
    "shadps4/video_core/buffer_cache/buffer_cache.cpp",
    "shadps4/video_core/buffer_cache/buffer_cache.h",
    "shadps4/video_core/renderer_vulkan/vk_staging_buffer_pool.cpp",
)

class PcStreamingAndroid(unittest.TestCase):
    def test_enabled_without_ui_bloat(self):
        sh=(ROOT/"ports/sotc/android/run-sotc-bionic.sh").read_text()
        j=(ROOT/"android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java").read_text()
        ui=(ROOT/"android-launcher/app/src/main/java/com/gow3/android/ui/SotcScreen.kt").read_text()
        for key,value in [("SOTC_STAGING_LARGE_POW2","1"),
                          ("SOTC_STAGING_LARGE_KEEP_MB","128"),
                          ("SOTC_BUF_ASYNC_KB","256")]:
            self.assertIn("export "+key+"="+value,sh)
            self.assertIn('env.put("'+key+'","'+value+'");',j)
        self.assertIn("export SOTC_COPY_BATCH=1",sh)
        self.assertIn("export SOTC_RB_NARROW=64",sh)
        for key in ("sotc_fast_bind","sotc_rb_stream","sotc_async_shaders",
                    "sotc_stage_spec_memo","sotc_record_thread","sotc_rb_async"):
            self.assertNotIn('save("'+key+'",',ui)
        for key in ("sotc_bachata_bloom","sotc_bachata_ssr","sotc_bachata_fog",
                    "sotc_bachata_shadows","sotc_blur_suppression"):
            self.assertIn('save("'+key+'",',ui)

    @unittest.skipUnless((UPSTREAM/"shadps4").is_dir(),"Pinned SotC GPU checkout required")
    def test_staged_real_gpu_cpp_guards(self):
        with tempfile.TemporaryDirectory() as td:
            dest=Path(td)/"gpu"
            for rel in GPU_FILES:
                (dest/rel).parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(UPSTREAM/rel,dest/rel)
            patch_pc_streaming(dest)
            cache=(dest/GPU_FILES[0]).read_text()
            header=(dest/GPU_FILES[1]).read_text()
            staging=(dest/GPU_FILES[2]).read_text()
            # Async never runs with an incoherent buffer, and the original sync
            # fallback remains. All queued uploads finish before submit/readback.
            self.assertIn("staging.buffer->is_coherent",cache)
            self.assertIn("BbCopy::Async(",cache)
            self.assertIn("BbCopy::WaitAsync();",cache)
            self.assertIn("void BufferCache::SubmitPendingArenaBinds",cache)
            self.assertIn("void BufferCache::ApplyDownloads",cache)
            self.assertIn("void BufferCache::JoinAsyncUploads()",cache)
            self.assertIn("std::atomic<bool> async_uploads{}",header)
            self.assertIn("SotcStagingLargePow2",staging)
            self.assertIn("SotcStagingLargeKeepBytes",staging)
            self.assertIn("return (v ? std::strtoull(v, nullptr, 10) : 128ULL) << 20;",staging)
            self.assertIn("scheduler.IsFree(entry.tick)",staging)
            self.assertIn("entry.held",staging)
            with self.assertRaisesRegex(ValueError,"source drift"):
                patch_pc_streaming(dest)

if __name__=="__main__":
    unittest.main()
