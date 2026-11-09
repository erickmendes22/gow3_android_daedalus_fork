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
    def test_scene_cap_is_bounded_160_mib_expansion_with_etc2_retention(self):
        # Nov 8 ETC2 pool retained 15 MiB with ZERO trim_limit and
        # ZERO purge_budget. 256 MiB is ceiling, not observed occupancy.
        bc_old=128;rgba_old=64;bc_new=256;rgba_new=96
        self.assertEqual((bc_new+rgba_new)-(bc_old+rgba_old),160)
        self.assertIn("BcPoolLimit = 128ULL * 1024 * 1024",IMAGE)
        self.assertIn("Rgba128PoolLimit = 64ULL * 1024 * 1024",IMAGE)
        self.assertIn("BcScenePoolLimit = 256ULL * 1024 * 1024",IMAGE)
        self.assertIn("Rgba128ScenePoolLimit = 96ULL * 1024 * 1024",IMAGE)
        self.assertIn("ScenePoolMaxEntries = 64",IMAGE)
        self.assertIn("BcPoolMaxEntries = 24",IMAGE)
        self.assertIn("Rgba128PoolMaxEntries = 24",IMAGE)
        self.assertIn("if (ScenePoolRetentionEnabled())",IMAGE)
        self.assertIn("return value && value[0] == '1';",IMAGE)
        self.assertIn("GOW3_MALI_SCENE_IMAGE_RETENTION",IMAGE)

    def test_etc2_is_already_in_bc_pool_and_reports_current_retained_memory(self):
        self.assertIn("((bc_pool_enabled && info.props.is_block)", IMAGE)
        self.assertIn("bool IsEtc2Image(const VkImageCreateInfo& ci)", IMAGE)
        self.assertIn("VK_FORMAT_ETC2_R8G8B8A8_UNORM_BLOCK", IMAGE)
        self.assertIn("VK_FORMAT_ETC2_R8G8B8A8_SRGB_BLOCK", IMAGE)
        self.assertIn("GOW3_ETC2_IMAGE_POOL hits=", IMAGE)
        self.assertIn("pool.etc2_hits", IMAGE)
        self.assertIn("pool.etc2_misses", IMAGE)
        self.assertIn("pool.etc2_stored", IMAGE)
        self.assertIn("pool.bytes >> 20", IMAGE)
        self.assertIn("if (pool.bytes + bytes > PoolLimit(raw)) return false;", IMAGE)
        self.assertIn("BcPoolHasBudget(allocator)", IMAGE)
        self.assertIn("budgets[i].usage * 10 > budgets[i].budget * 9", IMAGE)

    def test_completed_clean_image_can_return_to_pool_without_an_extra_tick(self):
        # The source previously queued ALL image frees against the current
        # command-buffer tick. A BC image whose last submitted GPU use is
        # already complete can instead become available to exact-create
        # recycling immediately during a BC/RGBA guest-layout transition.
        start = TEXTURE.index("void TextureCache::DeleteImage(ImageId image_id, bool completed_layout_alias)")
        body = TEXTURE[start:]
        for condition in (
            'std::getenv("GOW3_MALI_EAGER_COMPLETED_RETIRE")',
            'std::getenv("GOW3_MALI_CPU_PRESENT")',
            "vendorID == 0x13B5",
            "std::this_thread::get_id() == liverpool->GetGpuCommandProcessorThread()",
            'std::getenv("GOW3_DRAW_PIPE")',
            "!image.binding.is_target && !image.binding.is_bound",
            "image.tick_accessed_last != 0",
            "ImageFlagBits::GpuDirty | ImageFlagBits::GpuModified",
            "scheduler.GetWorkSemaphore()->IsFree(image.tick_accessed_last)",
            "reclaim();",
            "scheduler.DeferOperation(std::move(reclaim))",
        ):
            self.assertIn(condition, body)
        # The original unconditional fast path could free an image after
        # CopyImage() recorded a NEW use on the current (unsubmitted) tick.
        self.assertIn("completed_layout_alias && mali_eager_completed_retire", body)
        self.assertIn("FreeImage(cache_image_id, clean_alias_retirable);", TEXTURE)
        header = (ROOT / "gpu/shadps4/video_core/texture_cache/texture_cache.h").read_text()
        self.assertIn("void FreeImage(ImageId image_id, bool completed_layout_alias = false)", header)
        self.assertIn("DeleteImage(image_id, completed_layout_alias);", header)
        expand = TEXTURE.split("ImageId TextureCache::ExpandImage", 1)[1].split(
            "ImageId TextureCache::FindImage", 1)[0]
        self.assertIn("runtime.CopyImage(&src_image, &new_image);", expand)
        self.assertIn("FreeImage(image_id);", expand)
        self.assertNotIn("FreeImage(image_id, true)", expand)
        self.assertIn('GOW3_MALI_EAGER_COMPLETED_RETIRE:-1', RUN)
        self.assertIn('eager_completed_retire=$GOW3_MALI_EAGER_COMPLETED_RETIRE', RUN)
        self.assertLess(body.index("reclaim();"), body.index("scheduler.DeferOperation(std::move(reclaim))"))
        # Do not introduce blocking waits or GPU-wide drains in image cleanup.
        self.assertNotIn("scheduler.Finish();", body)
        self.assertNotIn("waitIdle()", body)
        self.assertNotIn("GetWorkSemaphore()->Refresh()", body)
        # The normal Vulkan recording worker is ON for the Android presenter.
        # Its submission synchronizes recording before the GPU can signal the
        # completed image tick, so the early-free path must not be disabled
        # whenever IsRecordingDeferred() happens to be true.
        self.assertNotIn("!scheduler.IsRecordingDeferred()", body)
        scheduler = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_scheduler.cpp").read_text()
        submit = scheduler.split("void Scheduler::SubmitExecution", 1)[1]
        self.assertLess(submit.index("SyncRecording();"),
                        submit.index("GetGraphicsQueue().submit("))

    def test_mali_transient_images_have_independent_caps_and_retirement(self):
        for marker in (
            "TransientPoolLimit = 96ULL * 1024 * 1024",
            "TransientPoolEntryLimit = 16ULL * 1024 * 1024",
            "TransientPoolMaxEntries = 32",
            "VK_FORMAT_R8_UNORM",
            "VK_FORMAT_R8G8B8A8_UINT",
            "VK_FORMAT_R8G8B8A8_SRGB",
            "return GetTransientPool();",
            "ScenePoolRetentionEnabled()",
            "IsTransientImage(static_cast<VkImageCreateInfo>(image_ci))",
            "info.resources.layers == 1",
            "info.resources.levels == 1",
            "for (auto* target : {&GetBcPool(), &GetRgba128Pool(), &GetTransientPool()})",
            "ProtectLastRetiredEtc2(identical)",
            "ProtectLastRetiredTransient(identical)",
            "++best_pool->rebind_out;",
        ):
            self.assertIn(marker, IMAGE)
        self.assertIn("GOW3_MALI_TRANSIENT_IMAGE_POOL:-1", RUN)
        self.assertIn("transient_pool=$GOW3_MALI_TRANSIENT_IMAGE_POOL", RUN)
        self.assertIn("GOW3_MALI_TRANSIENT_REBIND_LAST:-0", RUN)
        self.assertIn("GOW3_FRAME_STATS:-1", RUN)
        # Pooling cannot bypass GPU-completion checks or the VMA fallback.
        self.assertIn("SameBcCreate(e.create, raw)", IMAGE)
        self.assertIn("VMA_ALLOCATION_CREATE_WITHIN_BUDGET_BIT", IMAGE)
        self.assertIn("vmaCreateImage(allocator, &image_ci_unsafe", IMAGE)

    def test_no_gpu_live_image_or_bad_format_reuse(self):
        self.assertIn("scheduler.DeferOperation(std::move(reclaim))",TEXTURE)
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
        self.assertIn("std::scoped_lock lock{bc.mutex, rgba.mutex, transient.mutex};",IMAGE)
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
        self.assertIn("GOW3_MALI_RGBA128_IMAGE_POOL:-1",RUN)
        self.assertIn("GOW3_MALI_BC_IMAGE_POOL:-1",RUN)

    def test_does_not_weaken_alias_gpu_modification_rules(self):
        self.assertNotIn("age_safe >= 2",IMAGE)
        self.assertNotIn("safe_to_delete = true",IMAGE)
        self.assertIn("ImagePoolFor(raw)",IMAGE)

if __name__=="__main__":
    unittest.main()
