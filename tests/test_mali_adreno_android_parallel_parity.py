"""Verify Android Adreno parity while preserving non-dropping Mali draws."""
from pathlib import Path
import unittest
R=Path(__file__).resolve().parents[1]
SH=(R/'tools/android/bionic/run-bionic.sh').read_text()
CPP=(R/'gpu/shadps4/video_core/renderer_vulkan/vk_pipeline_cache.cpp').read_text()
H=(R/'gpu/shadps4/video_core/renderer_vulkan/vk_pipeline_cache.h').read_text()
D=(R/'gpu/shadps4/video_core/renderer_vulkan/vk_draw_prep.cpp').read_text()
S=(R/'gpu/shadps4/video_core/renderer_vulkan/vk_scheduler.cpp').read_text()
class MaliParity(unittest.TestCase):
    def test_android_adreno_8_and_2_defaults(self):
        self.assertIn('GOW3_VK_MAX_IN_FLIGHT=${GOW3_VK_MAX_IN_FLIGHT:-8}',SH)
        # PanVK reverted its explicitly observed 1-worker baseline; Adreno
        # stays on the renderer's ordinary two-worker fallback.
        self.assertIn('GOW3_GPU_COMPILER_WORKERS=${GOW3_GPU_COMPILER_WORKERS:-1}',SH)
        self.assertIn('GOW3_VK_MAX_IN_FLIGHT=${GOW3_VK_MAX_IN_FLIGHT:-2}',SH)
        self.assertIn('work_semaphore.Wait(signal_value - MaxAndroidInFlightSubmissions);',S)
        self.assertIn('return u64{8};',S)
    def test_both_android_drivers_use_zero_prep_by_default(self):
        self.assertIn('GOW3_PREP_WORKERS=${GOW3_PREP_WORKERS:-0}',SH)
        self.assertIn('if (std::getenv("GOW3_ANDROID_PORT"))',D)
    def test_background_compile_never_skips_mali_first_draw(self):
        self.assertIn('GOW3_MALI_ASYNC_DRAW_WAIT=${GOW3_MALI_ASYNC_DRAW_WAIT:-0}',SH)
        self.assertIn('mali_async_draw_wait = false',H)
        self.assertIn('(!mali_sync_draws || mali_async_draw_wait)',CPP)
        self.assertIn('if (mali_async_draw_wait && program->pending)',CPP)
        self.assertIn('PublishGraphics(true);',CPP)
        self.assertIn('PublishShaders(true);',CPP)
        self.assertIn('if (ready != graphics_pipelines.end()) return ready->second.get();',CPP)
        self.assertIn('return GetProgram(sel, hw_stage, sw_stage, params, binding);',CPP)
        self.assertIn('if (!mali_async_draw_wait || queued) return {};',CPP)
if __name__=='__main__':unittest.main()
