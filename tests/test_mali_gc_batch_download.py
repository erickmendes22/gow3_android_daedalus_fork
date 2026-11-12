"""Mali dirty-image GC synchronization regression gates (no device FPS claim)."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "gpu/shadps4/video_core/texture_cache/texture_cache.cpp").read_text()

class TestMaliGcBatchDownload(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gc = SOURCE.split("void TextureCache::GarbageCollectImages() {",1)[1].split(
            "void TextureCache::GarbageCollectSamplers()",1)[0]

    def test_mali_only_with_explicit_opt_out(self):
        self.assertIn('std::getenv("GOW3_MALI_CPU_PRESENT")', self.gc)
        self.assertIn('std::getenv("GOW3_MALI_GC_BATCH_DOWNLOAD")', self.gc)
        self.assertIn("(!option || option[0] != '0')", self.gc)
        self.assertIn("if (download && mali_gc_batch_download)",self.gc)

    def test_record_before_single_gpu_wait_and_cpu_write(self):
        g=self.gc
        self.assertIn("RecordImageDownload(image_id)",g)
        fn=g.split("const auto flush_gc_writebacks = [&] {",1)[1].split(
            "const auto clean_up =",1)[0]
        positions=[fn.index(x) for x in (
            "scheduler.Finish();",
            "entry.download.staging.Invalidate();",
            "Core::Memory::Instance()->TryWriteBacking(",
            "runtime.GetStagingPool().FreeDeferred(entry.download.staging);",
            "FreeImage(entry.image_id);"
        )]
        self.assertEqual(positions,sorted(positions))
        self.assertEqual(fn.count("scheduler.Finish();"),1)

    def test_prevents_alias_reordering(self):
        self.assertIn("start < previous.image_end && previous.image_address < end",self.gc)
        self.assertIn("if (overlap || gc_pending.size() >= MaxGcBatchImages",self.gc)
        self.assertIn("flush_gc_writebacks();",self.gc)

    def test_bounded_staging_and_original_fallback(self):
        self.assertIn("MaxGcBatchBytes = 32ULL * 1024 * 1024",self.gc)
        self.assertIn("MaxGcBatchImages = 16",self.gc)
        self.assertIn("if (bytes > MaxGcBatchBytes)",self.gc)
        self.assertIn("DownloadImageMemory(image_id, true);",self.gc)
        self.assertIn("++gc_downloads;",self.gc)
        self.assertIn("++gc_evictions;",self.gc)

    def test_flushes_before_aggressive_second_scan_and_at_end(self):
        after=self.gc.split("lru_cache.ForEachItemBelow(gc_tick - ticks_to_destroy, clean_up);",1)[1]
        self.assertIn("flush_gc_writebacks();",after.split("if (total_used_memory >= critical_gc_memory)",1)[0])
        after2=after.split("if (total_used_memory >= critical_gc_memory)",1)[1]
        self.assertIn("flush_gc_writebacks();",after2.split("// gow3: evictions under memory pressure",1)[0])

    def test_already_validated_bulk_downloads_are_preserved(self):
        original=SOURCE.split("void TextureCache::ProcessDownloadImages()",1)[1].split(
            "std::optional<TextureCache::PendingDownload>",1)[0]
        self.assertIn("boost::container::small_vector<PendingDownload, 16> pending;",original)
        self.assertIn("RecordImageDownload(image_id)",original)
        self.assertIn("scheduler.Finish();",original)

if __name__=="__main__":
    unittest.main()
