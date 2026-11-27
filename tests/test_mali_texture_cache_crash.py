from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]
V = ROOT/"gpu/shadps4/video_core/renderer_vulkan"
T = V.parent/"texture_cache"
C = (T/"texture_cache.cpp").read_text()
R = (V/"vk_rasterizer.cpp").read_text()
RUN = (ROOT/"tools/android/bionic/run-bionic.sh").read_text()
class TextureCacheCrash(unittest.TestCase):
    def test_gpu_transfer_refreshes_last_use_tick(self):
        runtime=(V/"vk_runtime.cpp").read_text()
        for name in ("bool Runtime::Transit(", "void Runtime::SetBackingSamples("):
            body=runtime.split(name,1)[1].split("if (",1)[0]
            self.assertIn("image->tick_accessed_last = scheduler.CurrentTick();",body)
    def test_readback_demand_wait_does_not_hold_readback_mutex(self):
        b=C.split("bool TextureCache::ResolveReadbacks(",1)[1].split("void TextureCache::CancelReadbacks(",1)[0]
        self.assertIn("std::unique_lock lock{readback_mutex};",b)
        self.assertLess(b.index("lock.unlock();"),b.index("scheduler.Wait(tick);"))
        self.assertLess(b.index("scheduler.Wait(tick);"),b.index("lock.lock();"))
        self.assertIn("while (const u64 tick = pending_readbacks.RequiredTick",b)
        self.assertIn("RetireReadbacks();",b)
        self.assertIn("export GOW3_STALE_READBACK=0",RUN)
    def test_early_readback_only_submits_current_pending_tick(self):
        b=C.split("void TextureCache::SubmitPendingReadbacks()",1)[1].split("std::optional<TextureCache::PendingDownload>",1)[0]
        self.assertIn("pending_readbacks.NewestTick() == scheduler.CurrentTick()",b)
        self.assertIn("if (needs_submit) scheduler.Flush();",b)
        self.assertNotIn("scheduler.Finish()",b)
        self.assertIn("texture_cache.SubmitPendingReadbacks();",R)
    def test_upload_batch_not_across_guest_draws_or_stale_frames(self):
        self.assertIn("recorded_upload_bytes += mip_size;",C)
        runtime=(V/"vk_runtime.cpp").read_text()
        self.assertIn("texture_upload_batch_bytes += BufferImageCopySize(copy, dst->info.pixel_format);",runtime)
        self.assertIn("runtime.CurrentUploadBatchBytes()",C)
        self.assertEqual(R.count("texture_cache.MaybeSubmitTextureBatch();"),4)
        for b in ("true","false"):
            self.assertIn("ResetBindings("+b+");\n    texture_cache.MaybeSubmitTextureBatch();",R)
        self.assertIn("texture_upload_batch_tick == scheduler.CurrentTick()",runtime)
        self.assertIn("GOW3_MALI_TEXTURE_BATCH_MIB:-16",RUN)
    def test_cache_stability_defaults_preserve_exact_pools(self):
        for flag in ("GOW3_MALI_REBIND_RETIRED_MEMORY","GOW3_MALI_BC_ALIAS_RETIRE","GOW3_MALI_EAGER_COMPLETED_RETIRE","GOW3_TEXTURE_HELPER"):
            self.assertIn(flag+":-0",RUN)
        for flag in ("GOW3_MALI_BC_IMAGE_POOL","GOW3_MALI_RGBA128_IMAGE_POOL"):
            self.assertIn(flag+":-1",RUN)
        self.assertIn("GOW3_MALI_VMA_BLOCK_MIB:-128",RUN)
if __name__ == "__main__": unittest.main()
