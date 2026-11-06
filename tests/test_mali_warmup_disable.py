"""Regression guard: Mali's warmup=off must skip every persisted pipeline warmup."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MaliWarmupDisabledTests(unittest.TestCase):
    def test_mali_launcher_uses_safe_warmup_by_default(self):
        script = (ROOT / "tools/android/bionic/run-bionic.sh").read_text()
        self.assertIn("export GOW3_BACKGROUND_WARMUP=${GOW3_BACKGROUND_WARMUP:-1}", script)
        source = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_pipeline_serialization.cpp").read_text()
        self.assertIn("PipelineCache::StartSafeMaliWarmUp()", source)
        self.assertIn("const bool compatible = CheckCacheProfile();", source)
        self.assertIn("warm.threads = mali ? 1u", source)
        self.assertIn("vk::UniquePipelineCache mali_worker_cache;", source)
        self.assertIn("warm.mali_worker_cache ? *warm.mali_worker_cache : *pipeline_cache", source)
        self.assertIn("mergePipelineCaches(", source)
        self.assertIn("mali_driver_cache_restored", source)

    def test_panfrost_driver_hash_prevents_cross_driver_profile_clears(self):
        storage = (ROOT / "gpu/shadps4/video_core/cache_storage.cpp").read_text()
        self.assertIn('std::getenv("GOW3_VULKAN_DRIVER")', storage)
        self.assertIn('driver_path.filename() == "libvulkan_panfrost.so"', storage)
        self.assertIn('driver_id.size() == 64', storage)
        self.assertIn('"panvk-" + driver_id', storage)
        self.assertIn('std::filesystem::copy_options::skip_existing', storage)
        self.assertIn('entry.path().filename() != "profile.bin"', storage)
        self.assertIn('cache_path != legacy_path', storage)

    def test_presenter_does_not_fall_through_to_sync_warmup(self):

        src = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_presenter.cpp").read_text()
        key = 'const char* background_warmup = std::getenv("GOW3_BACKGROUND_WARMUP");'
        self.assertEqual(src.count(key), 1)
        tail = src.split(key, 1)[1]
        early = re.search(
            r"if\s*\(background_warmup\s*&&\s*\*background_warmup\s*==\s*'0'\)\s*\{\s*return;\s*\}",
            tail,
        )
        self.assertIsNotNone(early, "warmup=off must return from Presenter constructor")
        background = tail.find("StartBackgroundWarmUp()")
        synchronous = tail.find("GetPipelineCache().WarmUp(")
        self.assertGreater(background, early.end())
        self.assertGreater(synchronous, background)

    def test_live_pipeline_compilation_stays_enabled(self):
        src = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_pipeline_cache.cpp").read_text()
        self.assertIn("PipelineCache::GetGraphicsPipeline(", src)
        self.assertIn("PipelineCache::GetComputePipeline(", src)


if __name__ == "__main__":
    unittest.main()
