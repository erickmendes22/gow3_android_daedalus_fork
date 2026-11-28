from pathlib import Path
import unittest
R=Path(__file__).resolve().parents[1]
V=R/"gpu/shadps4/video_core/renderer_vulkan"
T=V.parent/"texture_cache"
S=(V/"vk_scheduler.cpp").read_text()
H=(V/"vk_scheduler.h").read_text()
C=(T/"texture_cache.cpp").read_text()
D=(V/"vk_rasterizer.cpp").read_text()
RT=(V/"vk_runtime.cpp").read_text()
class R10Priorities(unittest.TestCase):
    def test_real_submission_history_and_wait_caller(self):
        self.assertIn("work_semaphore.TraceSubmission(submit_history)",S)
        self.assertIn("work_semaphore.Wait(tick, caller)",S)
        self.assertIn("DumpSubmissionHistory(tick)",(V/"vk_semaphore.cpp").read_text())
        self.assertIn("ASSERT(num_wait_semas < wait_semas.size())",H)
        a=S.split("wait_stage_masks = {",1)[1].split("};",1)[0]
        self.assertEqual(a.count("eAllCommands"),4)
    def test_tiny_first_preserves_all_other_copies(self):
        a=D.split("void Rasterizer::ProcessDownloadImages()",1)[1].split("bool Rasterizer::IsMapped",1)[0]
        self.assertLess(a.index("ProcessDownloadImages(true)"),a.index("ProcessDownloadImages();"))
        self.assertLess(a.index("SubmitPendingReadbacks(true)"),a.index("ProcessDownloadImages();"))
        self.assertIn("if (tiny_only && !tiny(image_id))",C)
        self.assertIn("GOW3_TINY_CONSUMER",C)
        self.assertIn("GOW3_TINY_PRODUCER",D)
    def test_budget_wait_releases_locks_and_reselects(self):
        a=C.split("pending_readbacks.RequiredTickForSpace(size)",1)[1].split("if (auto copy",1)[0]
        self.assertLess(a.index("readback_lock.unlock()"),a.index("scheduler.Wait(required)"))
        self.assertLess(a.index("scheduler.Wait(required)"),a.index("it = download_images.begin()"))
        self.assertIn("pending_readbacks.HasExactVersion",C)
        self.assertIn("if (upcoming_writes) ++gpu_write_epoch",(T/"image.cpp").read_text())
    def test_descriptor_and_upload_paths(self):
        self.assertIn("if (!same_descriptors && !writes.empty())",S)
        self.assertIn("if (!same_push) cmdbuf.pushConstants",S)
        self.assertIn("RecordGraphicsOrdered",D)
        self.assertIn("stripe.bufferOffset += u64(y) * row_bytes",RT)
        self.assertIn("stripe.imageOffset.y += static_cast<s32>(y)",RT)
        self.assertIn("constexpr u64 stripe_budget = 16_MB",RT)
        self.assertIn("rgba184.extent.height = 184", (T/"image.cpp").read_text())
    def test_r11_preserves_strict_cpu_faults_and_canonical_state(self):
        header=(T/"texture_cache.h").read_text()
        self.assertIn("stale_readbacks || mali_exact_readback_ranges",header)
        self.assertIn("stale_readbacks && source == ReadbackSource::CpuWrite",C)
        self.assertIn("source == ReadbackSource::ImageRefresh",C)
        self.assertIn("source == ReadbackSource::ImageFree",C)
        self.assertIn("append(&info.range, sizeof(info.range))",S)
        self.assertIn("append(&info.imageLayout, sizeof(info.imageLayout))",S)
        self.assertNotIn("append(w.pImageInfo,",S)
        self.assertIn("scheduler.RecordGraphicsOrdered([this, memory = memory_barrier",RT)
        self.assertIn("mali_batch_commands >= command_budget",C)
        self.assertIn("mali_batch_tick != tick",C)
    def test_r11_tiny_prefetch_publication_and_dma_dependency(self):
        pre=C.split("void TextureCache::PrefetchTinyReadback",1)[1].split("TextureCache::TakeTinyPrefetch",1)[0]
        self.assertIn("scheduler.Flush();",pre)
        self.assertNotIn("WatchReadback<true>",pre)
        self.assertNotIn("TryWriteBacking",pre)
        self.assertNotIn("download_images.erase",pre)
        self.assertIn("pending_readbacks.NewestTick() > pre.tick",C)
        self.assertIn("pre.epoch != image.gpu_write_epoch",C)
        self.assertIn("copy_tick, copy->staging",C)
        self.assertIn("tracked_image.last_readback_tick = copy_tick",C)
        self.assertEqual(D.count("texture_cache.PrefetchTinyReadback(cb_descs[0].first)"),2)
        reset=D.split("void Rasterizer::ResetBindings",1)[1].split("bool Rasterizer::IsComputeMetaClear",1)[0]
        self.assertIn("runtime.CompleteUntrackedShaderAccess(is_compute)",reset)
        dependency=RT.split("void Runtime::CompleteUntrackedShaderAccess",1)[1].split("void Runtime::FlushBarriers",1)[0]
        self.assertIn("eShaderWrite",dependency)
        self.assertIn("FlushBarriers(true);",dependency)
    def test_r11_crash_breadcrumbs_without_gpu_waits(self):
        sem=(V/"vk_semaphore.cpp").read_text()
        sem_h=(V/"vk_semaphore.h").read_text()
        trace=S.split("void Scheduler::TraceWork",1)[1].split("void Scheduler::FlushNativeDrawBatch",1)[0]
        self.assertIn("summary.first_seq = seq",trace)
        self.assertIn("summary.last_seq = seq",trace)
        self.assertIn("std::array<WorkSummary, WorkKinds> categories",sem_h)
        self.assertIn("GOW3_SUBMIT_CATEGORY",sem)
        self.assertIn("GOW3_READBACK_FAILURE",sem)
        self.assertNotIn("waitSemaphores",trace)
        self.assertNotIn("printf",trace)
        self.assertIn("ReadbackWaitScope wait_context",C)
        self.assertIn("TraceWork(5, guest_base",RT)
        self.assertIn("TraceWork(10, dispatch_hash",D)
        self.assertIn("RetireReadbacks(false)",C)
    def test_r11_forced_split_and_bounded_black_probe(self):
        p=(V/"vk_presenter.cpp").read_text()
        a=(V/"vk_swapchain_ahb.cpp").read_text()
        b=RT.split("void Runtime::FlushBarriers",1)[1]
        self.assertIn("force_buffer_barrier && scheduler.IsRendering()",b)
        self.assertIn("eColorAttachmentWrite",b)
        self.assertIn("eDepthStencilAttachmentWrite",b)
        self.assertIn("visual_frame % 120 == 0",p)
        self.assertIn("GOW3_MALI_BLACK_SOURCE",p)
        self.assertIn("GOW3_MALI_BLACK_AHB",a)
        self.assertIn("GOW3_MALI_BLACK_DELIVERY",a)
        self.assertIn("mali_perf_sample, visual_sample",p)
    def test_r12_physical_prefetch_and_graphics_cache(self):
        pre=C.split("void TextureCache::PrefetchTinyReadback",1)[1].split("TextureCache::TakeTinyPrefetch",1)[0]
        take=C.split("TextureCache::TakeTinyPrefetch",1)[1].split("void TextureCache::ProcessDownloadImages",1)[0]
        self.assertIn("IsMaliExposureReadback(i)",pre)
        self.assertIn("i.resources.levels >= 1",C)
        self.assertIn("ImageFlagBits::CpuDirty | ImageFlagBits::GpuDirty",pre)
        self.assertIn("ImageFlagBits::CpuDirty | ImageFlagBits::GpuDirty",take)
        self.assertIn("pre.uid != image.image_uid",take)
        self.assertIn("pre.generation != image.alias_generation",take)
        self.assertIn("pre.epoch != image.gpu_write_epoch",take)
        self.assertIn("pre.backing != std::bit_cast<u64>(image.GetImage())",take)
        self.assertIn("tiny_prefetch_filter[reason]",pre)
        self.assertNotIn("WatchReadback<true>",pre)
        self.assertIn("GraphicsResourceCacheEnabled() || NativeDrawBatchEnabled()",S)
        self.assertIn("!NativeDrawBatchEnabled() && !GraphicsResourceCacheEnabled()",H)
        self.assertIn("scheduler.GraphicsResourceCacheEnabled()", (V/"vk_pipeline_common.cpp").read_text())
        self.assertIn("scheduler.RecordBatchState",D.split("void Rasterizer::EmitIndexBuffer()",1)[1].split("void Rasterizer::ResolveIndexBuffer",1)[0])
        self.assertIn("scheduler.RecordGraphicsOrdered([=, this]",D)
    def test_r13_cached_pipelines_and_no_redundant_dma_preflush(self):
        ser=(V/"vk_pipeline_serialization.cpp").read_text()
        pc=(V/"vk_pipeline_cache.cpp").read_text()
        self.assertIn("if (!has_keys && indexed)",ser)
        self.assertIn("SeedMaliWarmupCache(*private_cache)",ser)
        self.assertIn("MergeMaliWarmupCache(*warm.mali_worker_cache)",ser)
        self.assertIn("if (publish_ready_now) return;",ser)
        self.assertIn("PumpWarmUp(true)",pc)
        self.assertIn("mergePipelineCaches(cache, *pipeline_cache)",pc)
        self.assertIn("mergePipelineCaches(*pipeline_cache, cache)",pc)
        self.assertIn("needs_flush |= IsBufferAccessed(dst, dst_min, dst_max - dst_min, true)",RT)
        self.assertIn("mali_dma_access_pending = true;\n            runtime.FlushBarriers(true);",D)
        self.assertEqual(D.count("if (mali_dma_access_pending) {"),5)
        self.assertEqual(D.count("runtime.CompleteUntrackedShaderAccess(is_compute)"),1)
        self.assertIn("GOW3_MALI_PREPARE_CACHED_PIPELINES=${GOW3_MALI_PREPARE_CACHED_PIPELINES:-1}",(R/"tools/android/bionic/run-bionic.sh").read_text())
    def test_r13_partial_linear_upload_and_tiling_dependencies(self):
        self.assertIn("partial_linear_upload ? first_upload_byte : 0",C)
        self.assertIn("!image.info.props.is_tiled",C)
        self.assertIn("copy.bufferOffset = copy.bufferOffset - source_begin + offset",C)
        tile=(T/"tile_manager.cpp").read_text()
        self.assertIn("runtime.IsBufferAccessed(in_buffer, in_offset, info.guest_size)",tile)
        self.assertIn("runtime.IsBufferAccessed(out_buffer, out_offset, info.guest_size, true)",tile)
        self.assertIn("runtime.AccessBuffer(in_buffer, in_offset, info.guest_size",tile)
        self.assertIn("return !image_barriers.empty();",RT)
        self.assertIn("last_state.pl_stage |= dst_stage",(T/"image.cpp").read_text())
    def test_r13_padded_exposure_exact_bytes(self):
        policy=C.split("static bool IsMaliExposureReadback",1)[1].split("TextureCache::TextureCache",1)[0]
        self.assertIn("i.pitch >= 1",policy)
        self.assertNotIn("i.pitch == 1",policy)
        self.assertIn("i.num_bits == 32",policy)
        self.assertIn("i.guest_size >= 4",policy)
        self.assertIn("if (mali && IsMaliExposureReadback(i)) return 4;",policy)
        self.assertIn("ImageDownloadBytes(i, mali_exact_readback_ranges) <= 64",C)
        self.assertIn("const u64 size = ImageDownloadBytes(image.info, mali_exact_readback_ranges)",C)
        self.assertEqual(C.count("const u32 download_size = ImageDownloadBytes(image.info, mali_exact_readback_ranges)"),2)
        self.assertEqual(C.count(".bufferRowLength = compact_exposure ? 0u : image.info.pitch"),2)
        self.assertIn("GOW3_MALI_EXPOSURE_COPY",C)
        self.assertIn("pre.copy.size != size",C)
        self.assertIn("WatchReadback<true>",C)
    def test_heavy_submit_breadcrumbs_and_compressed_copy_footprint(self):
        self.assertIn("info.diagnostic_upload_bytes = upload_bytes",C)
        self.assertIn("info.diagnostic_upload_bytes >= 16ull * 1024 * 1024",S)
        for phase in ("callback-begin","callback-end","recorder-begin","recorder-end",
                      "host-copies-end","throttle-end","driver-submit-begin","driver-submit-end",
                      "new-command-buffer","complete"):
            self.assertIn(f'heavy_phase("{phase}")',S)
        self.assertIn("((row_length + block[0] - 1) / block[0])",RT)
        self.assertIn("((height + block[1] - 1) / block[1])",RT)
        self.assertIn("partial_linear_upload = partial_linear_enabled &&",C)
    def test_image_copy_never_faults_on_unrelated_readback(self):
        bc=(V.parent/"buffer_cache/buffer_cache.cpp").read_text()
        mem=(R/"src/runtime_memory.c").read_text()
        p=bc.split("BufferCache::ObtainBufferForImage(",1)[1].split("bool BufferCache::IsRegionCpuModified",1)[0]
        self.assertLess(p.index("ResolveReadbacks("),p.index("IsRegionGpuModified("))
        self.assertLess(p.index("IsRegionGpuModified("),p.index("resolved_backing ="))
        self.assertIn("return ObtainBuffer(device_addr, size, false)",p)
        self.assertIn("resolved_backing ? &RunResolvedImageCopy : &RunGuestCopy",p)
        self.assertIn("memory->CopyResolvedImageBacking",p)
        impl=mem.split("void runtime_memory_read_backing_sparse",1)[1].split("int runtime_memory_write_backing",1)[0]
        self.assertLess(impl.index("read_lock();"),impl.index("memcpy(dst,backing_base"))
        self.assertLess(impl.index("memcpy(dst,backing_base"),impl.index("read_unlock();"))
        self.assertIn("memset(dst,0,n)",impl)
        self.assertNotIn("(void *)address",impl)
        self.assertIn("[this, &gpu_tick]",(V/"vk_resource_pool.cpp").read_text())
if __name__=="__main__": unittest.main()
