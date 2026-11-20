"""Source guards for the PanVK G720 heavy-scene corrections (not a device FPS test)."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

def src(path):
    return (ROOT / path).read_text(encoding="utf-8")

class MaliFreezeHeavySceneRegression(unittest.TestCase):
    def test_async_redraw_never_waits_for_an_inflight_cpu_present(self):
        p = src("gpu/shadps4/video_core/renderer_vulkan/vk_presenter.cpp")
        prepare = p[p.index("Frame* Presenter::PrepareLastFrame()"):p.index("void Presenter::", p.index("Frame* Presenter::PrepareLastFrame()"))]
        self.assertIn("if (mali_cpu_async)", prepare)
        self.assertIn("mali_cpu_inflight[frame->id] != 0", prepare)
        self.assertIn("getFenceStatus(frame->present_done)", prepare)
        self.assertLess(prepare.index("getFenceStatus(frame->present_done)"),
                        prepare.index("waitForFences(frame->present_done"))
        present = p[p.index("void Presenter::Present(Frame* frame,"):p.index("void Presenter::PollLsfgState()", p.index("void Presenter::Present(Frame* frame,"))]
        self.assertIn("if (mali_cpu_async && is_reusing_frame)", present)
        self.assertNotIn("mali_cpu_jobs_cv.wait(lock", present)
        self.assertIn("mali_cpu_inflight[frame->id] != 0) return;", present)

    def test_readback_wait_is_timed_but_frame_lifetime_remains_guarded(self):
        p = src("gpu/shadps4/video_core/renderer_vulkan/vk_presenter.cpp")
        worker = p[p.index("void Presenter::CompleteMaliCpuPresentation("):p.index("bool Presenter::IsVideoOutSurface(")]
        self.assertIn("waitForFences(frame->present_done, true, 100'000'000ull)", worker)
        self.assertIn("while (done == vk::Result::eTimeout)", worker)
        self.assertIn("GOW3_MALI_PRESENT_FENCE_STALL", worker)
        self.assertIn("ASSERT_MSG(done == vk::Result::eSuccess", worker)
        self.assertLess(worker.index("ASSERT_MSG(done == vk::Result::eSuccess"),
                        worker.index("vmaInvalidateAllocation("))
        self.assertLess(worker.index("vmaInvalidateAllocation("),
                        worker.index("free_queue.push(frame)"))

    def test_gpu_tick_wait_does_not_hold_cross_scheduler_submit_lock(self):
        c = src("gpu/shadps4/video_core/renderer_vulkan/vk_scheduler.cpp")
        fn = c[c.index("void Scheduler::SubmitExecution("):c.index("void Scheduler::PriorityPendingOpsThread(", c.index("void Scheduler::SubmitExecution("))]
        self.assertIn("work_semaphore.CurrentTick()", fn)
        self.assertIn("work_semaphore.Wait(next_signal_value - MaxAndroidInFlightSubmissions)", fn)
        self.assertLess(fn.index("work_semaphore.Wait(next_signal_value"),
                        fn.index("std::unique_lock lk{submit_mutex}"))
        self.assertLess(fn.index("std::unique_lock lk{submit_mutex}"),
                        fn.index("work_semaphore.NextTick()"))
        self.assertIn("lk.unlock();", fn)
        self.assertIn("work_semaphore.Wait(retire_tick)", fn)
        self.assertIn("work_semaphore.IsFree(retire_tick)", fn)
        self.assertLess(fn.index("lk.unlock();"),
                        fn.index("work_semaphore.Wait(retire_tick)"))

    def test_rgba128_exact_shape_survives_cross_format_rebind(self):
        c = src("gpu/shadps4/video_core/texture_cache/image.cpp")
        self.assertIn("const bool rgba128 = IsRgba128Image(candidate.create);", c)
        self.assertIn("if (!etc2 && !rgba128 && !transient_image) return false;", c)
        self.assertIn("(etc2 || rgba128) ? ProtectLastRetiredEtc2(identical)", c)
        for height in (168, 208, 232):
            self.assertIn(f"rgba{height}.extent.height = {height};", c)
        self.assertIn("GOW3_MALI_VMA_PREWARM_HEAVY", c)
        self.assertIn("BcPoolHasBudget(allocator)", c)
        self.assertIn("SameBcCreate(e.create, raw)", c)
        # Approximate raw RGBA128 payload of new shapes + previous 248px
        self.assertLessEqual(4096*16*(168+208+232+248), 96*1024*1024)

    def test_shader_stage_barriers_keep_storage_and_write_hazards(self):
        raster = src("gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp")
        image = src("gpu/shadps4/video_core/texture_cache/image.cpp")
        self.assertIn('GOW3_MALI_SHADER_STAGE_BARRIERS', raster)
        self.assertIn("(!selected || selected[0] != '0')", raster)
        sampled = raster[raster.index("if (is_storage) {", raster.index("void Rasterizer::BindTextures(")):]
        self.assertIn("eAllCommands", sampled[:600])
        self.assertIn("MaliReadOnlyTextureStage(stage.sw_stage)", sampled[:1200])
        self.assertIn("last_state.access_mask |= dst_mask;", image)
        self.assertIn("last_state.pl_stage |= dst_stage;", image)
        self.assertIn("const bool upcoming_writes", image)

    def test_only_read_only_vs_fs_uniforms_get_precise_stage(self):
        c = src("gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp")
        h = src("gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.h")
        self.assertIn("bool is_uniform;", h)
        self.assertIn("Shader::SwStage shader_stage;", h)
        self.assertIn("uniform, stage.sw_stage", c)
        self.assertIn("precise_mali_ubo && is_uniform && !is_written && !is_compute", c)
        self.assertIn("vk::PipelineStageFlagBits2::eVertexShader", c)
        self.assertIn("vk::PipelineStageFlagBits2::eFragmentShader", c)
        self.assertIn("GOW3_MALI_PRECISE_UBO_BARRIERS", c)
        self.assertIn("eAllGraphics", c)

if __name__ == "__main__":
    unittest.main()
