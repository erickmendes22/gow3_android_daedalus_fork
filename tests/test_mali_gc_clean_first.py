"""Regression guard for Mali dirty-texture GC under the G720 memory-pressure log."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / "gpu/shadps4/video_core/texture_cache/texture_cache.cpp").read_text()
HDR = (ROOT / "gpu/shadps4/video_core/texture_cache/texture_cache.h").read_text()
SH = (ROOT / "tools/android/bionic/run-bionic.sh").read_text()


class MaliGcCleanFirstTests(unittest.TestCase):
    def test_only_mali_cpu_present_default_and_rollback(self):
        self.assertIn("GOW3_MALI_GC_CLEAN_FIRST=${GOW3_MALI_GC_CLEAN_FIRST:-1}", SH)
        self.assertIn('std::getenv("GOW3_MALI_CPU_PRESENT")', SRC)
        self.assertIn('std::getenv("GOW3_MALI_GC_CLEAN_FIRST")', SRC)
        self.assertIn("(!option || option[0] != '0')", SRC)

    def test_no_dirty_image_discard_without_writeback(self):
        start = SRC.index("void TextureCache::GarbageCollectImages()")
        end = SRC.index("void TextureCache::GarbageCollectSamplers()")
        gc = SRC[start:end]
        self.assertIn("const bool download = image.SafeToDownload()", gc)
        self.assertIn("if (mali_clean_first_gc && download && !aggresive", gc)
        self.assertIn("pressure_gc_memory + (critical_gc_memory - pressure_gc_memory) / 2", gc)
        self.assertLess(gc.index("++gc_dirty_deferred;"), gc.index("DownloadImageMemory(image_id, true)"))
        self.assertLess(gc.index("DownloadImageMemory(image_id, true)"), gc.index("FreeImage(image_id);"))
        self.assertIn("if (total_used_memory >= critical_gc_memory)", gc)
        self.assertIn("configure(true);", gc)

    def test_skipped_candidates_do_not_consume_quota_or_sync(self):
        gc = SRC[SRC.index("void TextureCache::GarbageCollectImages()"):]
        self.assertLess(gc.index("if (tiled && download)"), gc.index("--num_deletions;"))
        self.assertLess(gc.index("if (download && !pressured)"), gc.index("--num_deletions;"))
        self.assertLess(gc.index("++gc_dirty_deferred;"), gc.index("--num_deletions;"))
        self.assertLess(gc.index("++gc_dirty_deferred;"), gc.index("ReadbackSource::CacheCleanup"))
        self.assertIn("gc_dirty_deferred = 0", HDR)
        self.assertIn("dirty kept since last report", SRC)

    def test_existing_writeback_is_still_synchronous(self):
        self.assertIn("DownloadImageMemory(image_id, true);", SRC)
        self.assertIn("scheduler.Finish();", SRC)


if __name__ == "__main__":
    unittest.main()
