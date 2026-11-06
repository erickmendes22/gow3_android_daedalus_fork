"""Mali-only image format-cache and observational PM4 profiler guards."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
I=(ROOT/'gpu/shadps4/video_core/texture_cache/image.cpp').read_text()
S=(ROOT/'gpu/shadps4/video_core/renderer_vulkan/vk_mali_perf_stats.h').read_text()
P=(ROOT/'gpu/shadps4/video_core/amdgpu/liverpool.cpp').read_text()
class MaliFormatCachePM4Tests(unittest.TestCase):
    def test_adreno_stays_unchanged_and_pnext_never_cached(self):
        for s in ('vendorID != 0x13B5', 'info.pNext',
                  'GOW3_MALI_IMAGE_FORMAT_QUERY_CACHE', '(toggle && toggle[0] == \'0\')',
                  'getImageFormatProperties2(info)'):
            self.assertIn(s,I)
        self.assertEqual(I.count('getImageFormatProperties2('),1)
    def test_exact_query_signature_and_outcome(self):
        for s in ('entry.device == device','entry.format == info.format',
                  'entry.type == info.type','entry.tiling == info.tiling',
                  'entry.usage == info.usage','entry.flags == info.flags',
                  'static thread_local std::vector<Entry> entries',
                  'entries.size() >= 256', 'vk::Result::eErrorFormatNotSupported',
                  'image_format_properties.samples', 'ProbeImageFormat(instance, format_info)',
                  'MaliPerfStats::Stage::ImageVkAllocate', 'vmaCreateImage(allocator, &image_ci_unsafe'):
            self.assertIn(s,I)
    def test_pool_miss_and_budget_reasons_are_distinct(self):
        for key in ('GOW3_%s_IMAGE_POOL_DIAG', 'miss_empty', 'miss_incompatible',
                    'trim_limit', 'purge_budget', 'reject_budget',
                    '++pool.miss_empty;', '++pool.miss_incompatible;',
                    '++pool.trim_limit;', '++pool.purge_budget;'):
            self.assertIn(key, I)
    def test_pm4_profile_no_wait_removal(self):
        for s in ('SamplePm4Resume()', 'Pm4ResumeBlocked', 'Pm4ResumeWork',
                  'Pm4WaitReason::WaitRegMem','Pm4WaitReason::MemorySemaphore',
                  'Pm4WaitReason::Rewind','YIELD_GFX();','gfx_blocked_fiber_wait = false;'):
            self.assertIn(s,P)
        for s in ('image_vk_allocate','image_format_query','pm4_yield_wait_regmem_s256'):
            self.assertIn(s,S)
if __name__=='__main__':unittest.main()
