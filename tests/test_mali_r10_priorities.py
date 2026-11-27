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
        self.assertIn("scheduler.RecordGraphicsOrdered([memory = memory_barrier",RT)
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
if __name__=="__main__": unittest.main()
