"""G720 scene-transition pool expansion is bounded, driver-specific and reversible.

Measured cause: log 20261106-064553.zip had 148 BC pool hits / 492 misses,
264 drops and >400 ms creation spikes. Exact scene-size reuse is still a
hypothesis to be confirmed by the tester; this test never asserts game FPS.
"""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
IMAGE=(ROOT/"gpu/shadps4/video_core/texture_cache/image.cpp").read_text()
RUN=(ROOT/"tools/android/bionic/run-bionic.sh").read_text()
TEXTURE=(ROOT/"gpu/shadps4/video_core/texture_cache/texture_cache.cpp").read_text()

class MaliSceneRetentionTests(unittest.TestCase):
    def test_scene_cap_is_only_a_controlled_96_mib_expansion(self):
        bc_old=128;rgba_old=64;bc_new=192;rgba_new=96
        self.assertEqual((bc_new+rgba_new)-(bc_old+rgba_old),96)
        self.assertIn("BcPoolLimit = 128ULL * 1024 * 1024",IMAGE)
        self.assertIn("Rgba128PoolLimit = 64ULL * 1024 * 1024",IMAGE)
        self.assertIn("BcScenePoolLimit = 192ULL * 1024 * 1024",IMAGE)
        self.assertIn("Rgba128ScenePoolLimit = 96ULL * 1024 * 1024",IMAGE)
        self.assertIn("ScenePoolMaxEntries = 48",IMAGE)
        self.assertIn("BcPoolMaxEntries = 24",IMAGE)
        self.assertIn("Rgba128PoolMaxEntries = 24",IMAGE)
        self.assertIn("if (ScenePoolRetentionEnabled())",IMAGE)
        self.assertIn("return value && value[0] == '1';",IMAGE)
        self.assertIn("GOW3_MALI_SCENE_IMAGE_RETENTION",IMAGE)

    def test_completed_clean_image_can_return_to_pool_without_an_extra_tick(self):
        # The source previously queued ALL image frees against the current
        # command-buffer tick. A BC image whose last submitted GPU use is
        # already complete can instead become available to exact-create
        # recycling immediately during a BC/RGBA guest-layout transition.
        start = TEXTURE.index("void TextureCache::DeleteImage(ImageId image_id)")
        body = TEXTURE[start:]
        for condition in (
            'std::getenv("GOW3_MALI_EAGER_COMPLETED_RETIRE")',
            'std::getenv("GOW3_MALI_CPU_PRESENT")',
            "vendorID == 0x13B5",
            "std::this_thread::get_id() == liverpool->GetGpuCommandProcessorThread()",
            "!scheduler.IsRecordingDeferred()",
            "!image.binding.is_target && !image.binding.is_bound",
            "image.tick_accessed_last != 0",
            "ImageFlagBits::GpuDirty | ImageFlagBits::GpuModified",
            "scheduler.GetWorkSemaphore()->IsFree(image.tick_accessed_last)",
            "reclaim();",
            "scheduler.DeferOperation(std::move(reclaim))",
        ):
            self.assertIn(condition, body)
        self.assertIn('GOW3_MALI_EAGER_COMPLETED_RETIRE:-1', RUN)
        self.assertIn('eager_completed_retire=$GOW3_MALI_EAGER_COMPLETED_RETIRE', RUN)
        self.assertLess(body.index("reclaim();"), body.index("scheduler.DeferOperation(std::move(reclaim))"))
        # Do not introduce blocking waits or GPU-wide drains in image cleanup.
        self.assertNotIn("scheduler.Finish();", body)
        self.assertNotIn("waitIdle()", body)
        self.assertNotIn("GetWorkSemaphore()->Refresh()", body)

    def test_no_gpu_live_image_or_bad_format_reuse(self):
        self.assertIn("scheduler.DeferOperation([this, image_id]",TEXTURE)
        self.assertIn("e.allocator == allocator && SameBcCreate(e.create, raw)",IMAGE)
        for field in ("a.format == b.format","a.samples == b.samples",
                      "a.tiling == b.tiling","a.mipLevels == b.mipLevels",
                      "a.usage == b.usage","a.extent.width == b.extent.width"):
            self.assertIn(field,IMAGE)
        self.assertIn("if (!recycle_bc || !ReturnBcImage",IMAGE)
        self.assertIn("vmaCreateImage(allocator, &image_ci_unsafe",IMAGE)

    def test_memory_pressure_guard_still_applies(self):
        self.assertIn("BcPoolHasBudget(allocator)",IMAGE)
        self.assertIn("budgets[i].usage * 10 > budgets[i].budget * 9",IMAGE)
        self.assertIn("if (!BcPoolHasBudget(allocator))",IMAGE)
        self.assertIn("TrimBcPool(pool, bytes, raw);",IMAGE)
        self.assertIn("if (pool.bytes + bytes > PoolLimit(raw)) return false;",IMAGE)
        self.assertIn("BcPoolEntryLimit = 64ULL * 1024 * 1024",IMAGE)
        self.assertIn("Rgba128PoolEntryLimit = 32ULL * 1024 * 1024",IMAGE)

    def test_pressure_reclaim_does_not_touch_live_or_compatible_images(self):
        self.assertIn("void ReclaimIdleImagesBeforeAllocate(",IMAGE)
        self.assertIn("if (!ScenePoolRetentionEnabled()) return;",IMAGE)
        self.assertIn("budgets[i].usage * 100 >= budgets[i].budget * 82",IMAGE)
        self.assertIn("std::scoped_lock lock{bc.mutex, rgba.mutex};",IMAGE)
        self.assertIn("candidate.allocator != allocator ||",IMAGE)
        self.assertIn("SameBcCreate(candidate.create, requested)",IMAGE)
        self.assertIn("max_reclaim = 64ULL * 1024 * 1024",IMAGE)
        self.assertIn("ReclaimIdleImagesBeforeAllocate(allocator, image_ci_unsafe);",IMAGE)
        # Match the reference PanVK 100 ms memory-budget cadence without
        # weakening the per-VkImage VMA WITHIN_BUDGET safety check.
        self.assertIn("next_budget_check = now + std::chrono::milliseconds(100);",IMAGE)
        self.assertIn("if (now < next_budget_check) return;",IMAGE)
        self.assertIn("VMA_ALLOCATION_CREATE_WITHIN_BUDGET_BIT",IMAGE)
        self.assertIn("GOW3_MALI_SLOW_IMAGE_ALLOC",IMAGE)
        self.assertIn("GOW3_MALI_IMAGE_PREALLOC_RECLAIM",IMAGE)

    def test_launch_is_panvk_scoped_and_reversible(self):
        case=RUN.index('case "' + chr(36) + '{GOW3_VULKAN_DRIVER:-}" in')
        driver=RUN.index("*/libvulkan_panfrost.so)",case)
        setting=RUN.index("export GOW3_MALI_SCENE_IMAGE_RETENTION=",driver)
        closing=RUN.index("# End Mali PanVK safe profile.",setting)
        self.assertLess(setting,closing)
        self.assertIn("GOW3_MALI_SCENE_IMAGE_RETENTION:-1",RUN)
        self.assertIn("scene_retention=$GOW3_MALI_SCENE_IMAGE_RETENTION",RUN)
        self.assertIn("GOW3_MALI_RGBA128_IMAGE_POOL:-0",RUN)
        self.assertIn("GOW3_MALI_BC_IMAGE_POOL:-1",RUN)

    def test_does_not_weaken_alias_gpu_modification_rules(self):
        self.assertNotIn("age_safe >= 2",IMAGE)
        self.assertNotIn("safe_to_delete = true",IMAGE)
        self.assertIn("ImagePoolFor(raw)",IMAGE)

if __name__=="__main__":
    unittest.main()
