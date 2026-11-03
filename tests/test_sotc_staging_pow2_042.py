#!/usr/bin/env python3
"""Test the upstream SotC staging allocator backport on pinned native C++.

The change is isolated: 0.1.40 readbacks, Vulkan waits and GPU-modified
region tracking stay unchanged. Checks the production staging patcher output.
"""
from pathlib import Path
import tempfile
import shutil
import unittest
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"ports/sotc/android"))
from stage_sotc_staging_pow2 import patch_staging_pow2

SOURCE=ROOT/"upstream-sotc/gpu/shadps4/video_core/renderer_vulkan/vk_staging_buffer_pool.cpp"

class StagingReuse(unittest.TestCase):
    @unittest.skipUnless(SOURCE.exists(),"Pinned original renderer checkout unavailable")
    def test_stage_real_original_cpp_and_preserve_fences(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td)/"shadps4/video_core/renderer_vulkan"
            d.mkdir(parents=True)
            dst=d/"vk_staging_buffer_pool.cpp"
            shutil.copy2(SOURCE,dst)
            old=dst.read_text()
            self.assertNotIn("SOTC_STAGING_LARGE_POW2",old)
            patch_staging_pow2(Path(td))
            new=dst.read_text()
            self.assertNotEqual(new,old)
            self.assertIn('std::getenv("SOTC_STAGING_LARGE_POW2")',new)
            self.assertIn('std::getenv("SOTC_STAGING_LARGE_KEEP_MB")',new)
            self.assertIn(": 64ULL) << 20",new)
            self.assertIn('const bool pow2 = deferred || StagingLargePow2()',new)
            self.assertIn('pow2 ? std::bit_ceil(std::max(size, LARGE_MIN_GRANULARITY))',new)
            self.assertIn('pow2   ? alloc_size * 2',new)
            for guard in (
                'entry.held || entry_size < size || entry_size > max_size',
                '(!scheduler.IsFree(entry.tick) && !unsynchronized)',
                'best->held = deferred;',
                'ASSERT_MSG(it != cache.end() && it->held',
                'it->held = false;',
                'it->tick = scheduler.CurrentTick();',
                'entry.held || frame - entry.last_used_frame < LARGE_IDLE_FRAMES',
                '!scheduler.IsFree(entry.tick)',
                'std::ranges::sort(cache',
                'std::erase_if(cache',
            ):
                self.assertIn(guard,new)
            # Fail fast rather than replacing an unpinned third party version twice.
            with self.assertRaises(RuntimeError):
                patch_staging_pow2(Path(td))
            self.assertIn('StagingBufferRef StagingBufferPool::RequestFromRing(',new)
            self.assertEqual(new.count('StagingBufferPool::RequestLarge('),old.count('StagingBufferPool::RequestLarge('))
    def test_default_memory_limit_and_size_classes(self):
        # The exact same std::bit_ceil size-class rule that is staged into C++.
        def bitceil(x): return 1 << ((x-1).bit_length())
        sizes=[1<<16, (1<<16)+1, (1<<20)-1, (1<<20)+1, 20<<20, 200<<20]
        for request in sizes:
            allocated=bitceil(max(request,65536))
            self.assertGreaterEqual(allocated,request)
            self.assertLess(allocated,2*max(request,65536))
            self.assertEqual(allocated & (allocated-1),0)
        self.assertLessEqual(64<<20,256<<20)
    def test_launcher_original_toggles_unchanged(self):
        ui=(ROOT/"android-launcher/app/src/main/java/com/gow3/android/ui/SotcScreen.kt").read_text()
        java=(ROOT/"android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java").read_text()
        self.assertIn('values["sotc_rb_stream"]?:"1"',ui)
        self.assertIn('values["sotc_rb_async"]?:"0"',ui)
        self.assertIn('values["sotc_fast_bind"]?:"0"',ui)
        self.assertIn('env.put("BB_READBACKS",rbMode)',java)
        self.assertIn('env.put("SOTC_RB_STREAM_MAX_KB","512");',java)

if __name__=="__main__":
    unittest.main()
