"""Guard G720 VMA small blocks and copy-free BC/RGBA128 recycling.

The 2026-11-06 capture has a single 780.47 ms vmaCreateImage call,
192 RGBA128 creations / 334.8 MiB, but only 12 recycled RGBA128 images.
This is a source-level regression gate; it cannot assert device FPS.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
INSTANCE = (ROOT/"gpu/shadps4/video_core/renderer_vulkan/vk_instance.cpp").read_text()
IMAGE = (ROOT/"gpu/shadps4/video_core/texture_cache/image.cpp").read_text()
TEXTURE = (ROOT/"gpu/shadps4/video_core/texture_cache/texture_cache.cpp").read_text()
HEADER = (ROOT/"gpu/shadps4/video_core/texture_cache/texture_cache.h").read_text()
RUN = (ROOT/"tools/android/bionic/run-bionic.sh").read_text()


class MaliVkAllocationPolicy(unittest.TestCase):
    def test_32_mib_blocks_are_panvk_only_and_reversible(self):
        self.assertIn('preferred_block_size = 0;', INSTANCE)
        self.assertIn('properties.vendorID == 0x13B5', INSTANCE)
        self.assertIn('std::getenv("GOW3_ANDROID_PORT")', INSTANCE)
        self.assertIn('unsigned long mib = 0;', INSTANCE)
        self.assertIn('std::getenv("GOW3_MALI_VMA_BLOCK_MIB")', INSTANCE)
        self.assertIn('parsed == 0 || parsed == 16 || parsed == 32', INSTANCE)
        self.assertIn('.preferredLargeHeapBlockSize = preferred_block_size', INSTANCE)
        self.assertIn('VMA_ALLOCATOR_CREATE_BUFFER_DEVICE_ADDRESS_BIT', INSTANCE)

    def test_rgba_budget_reclaim_not_gated_by_exact_shape_pool(self):
        self.assertIn('const bool mali_rgba_cold_allocation =', IMAGE)
        self.assertIn('VK_FORMAT_R32G32B32A32_UINT', IMAGE)
        self.assertIn('if (recycle_bc || mali_rgba_cold_allocation)', IMAGE)
        self.assertIn('ReclaimIdleImagesBeforeAllocate(allocator, image_ci_unsafe)', IMAGE)
        self.assertIn('VMA_ALLOCATION_CREATE_WITHIN_BUDGET_BIT', IMAGE)
        # G615's 78ms non-BC/non-RGBA allocation must also be reported,
        # but VMA reclamation itself remains restricted to safe pool classes.
        self.assertIn('if ((recycle_bc || mali_rgba_cold_allocation ||', IMAGE)
        self.assertIn('Vulkan::MaliPerfStats::Enabled()) && allocation_ms >= 25.0)', IMAGE)
        self.assertIn('GOW3_MALI_SLOW_IMAGE_ALLOC ms=', IMAGE)
        self.assertIn('GOW3_MALI_RGBA128_IMAGE_POOL=${GOW3_MALI_RGBA128_IMAGE_POOL:-1}', RUN)

    def test_immediate_free_only_for_copy_free_completed_alias(self):
        self.assertIn('FreeImage(cache_image_id, clean_alias_retirable);', TEXTURE)
        self.assertIn('completed_layout_alias && mali_eager_completed_retire', TEXTURE)
        self.assertIn('void FreeImage(ImageId image_id, bool completed_layout_alias = false)', HEADER)
        self.assertIn('DeleteImage(image_id, completed_layout_alias);', HEADER)
        self.assertIn('scheduler.GetWorkSemaphore()->IsFree(image.tick_accessed_last)', TEXTURE)
        expand = TEXTURE.split('ImageId TextureCache::ExpandImage', 1)[1].split(
            'ImageId TextureCache::FindImage', 1)[0]
        self.assertIn('runtime.CopyImage(&src_image, &new_image);', expand)
        self.assertIn('FreeImage(image_id);', expand)
        self.assertNotIn('FreeImage(image_id, true);', expand)
        self.assertIn('scheduler.DeferOperation(std::move(reclaim));', TEXTURE)

    def test_no_format_reinterpretation(self):
        self.assertIn('a.format == b.format', IMAGE)
        self.assertIn('a.tiling == b.tiling', IMAGE)
        self.assertIn('a.extent.width == b.extent.width', IMAGE)
        self.assertIn('a.usage == b.usage', IMAGE)
        self.assertIn('GOW3_MALI_BC_IMAGE_POOL=${GOW3_MALI_BC_IMAGE_POOL:-1}', RUN)


if __name__ == "__main__":
    unittest.main()
