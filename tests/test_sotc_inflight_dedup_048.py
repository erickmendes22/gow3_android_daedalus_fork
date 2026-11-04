#!/usr/bin/env python3
"""Readback dedup: patched pinned GPU source and old path regression."""
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"ports/sotc/android"))
from stage_sotc_inflight_dedup_048 import patch_readback_dedup
class InflightDedup(unittest.TestCase):
    def test_gpu_source_unchanged_fences_and_protections(self):
        upstream=ROOT/"upstream-sotc/gpu/shadps4/video_core/buffer_cache"
        if not upstream.is_dir(): self.skipTest("pinned GPU checkout not available")
        with tempfile.TemporaryDirectory() as tmp:
            gpu=Path(tmp)/"shadps4/video_core/buffer_cache"
            gpu.mkdir(parents=True)
            for name in ("buffer_cache.cpp","buffer_cache.h"):
                shutil.copy2(upstream/name,gpu/name)
            before=(gpu/"buffer_cache.cpp").read_text()
            patch_readback_dedup(Path(tmp),ROOT)
            result=(gpu/"buffer_cache.cpp").read_text()
            assert "FindCoveringInflightReadback(readback.device_addr, readback.size)" in result
            assert 'std::getenv("SOTC_RB_INFLIGHT_DEDUP")' in result
            assert "readback.dependent = true;" in result
            assert result.index("FindCoveringInflightReadback(readback.device_addr") < result.index("GatherDownloads(arena, window_start, readback.window_size")
            for critical in ("scheduler.WaitSubmitted(readback.tick, false)",
                             "scheduler.GetWorkSemaphore()->Wait(readback.tick)",
                             "scheduler.Flush();",
                             "ApplyDownloads(readback.pending, download.mapped, download.offset)",
                             "SubtractDownloaded(readback.pending)",
                             "MarkInflightReadbacksDirty(device_addr, size)"):
                assert critical in result and critical in before,critical
            assert "if (candidate && !candidate->finished && !candidate->dirty" in result
            with self.assertRaisesRegex(RuntimeError,"already applied"):
                patch_readback_dedup(Path(tmp),ROOT)
    def test_old_options_preserved(self):
        script=(ROOT/"ports/sotc/android/run-sotc-bionic.sh").read_text()
        for key in ("SOTC_POOL_OWNER","SOTC_RB_HOT","SOTC_RB_STREAM","BB_READBACKS","SOTC_RB_ASYNC"):
            self.assertIn(key,script)
        self.assertIn('versionName = "0.1.48-inflight-rb-dedup"',(ROOT/"android-launcher/app/build.gradle.kts").read_text())
if __name__=="__main__":unittest.main()
