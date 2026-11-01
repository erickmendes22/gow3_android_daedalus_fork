"""Regression guard: Mali's warmup=off must skip every persisted pipeline warmup."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MaliWarmupDisabledTests(unittest.TestCase):
    def test_mali_launcher_explicitly_disables_warmup(self):
        script = (ROOT / "tools/android/bionic/run-bionic.sh").read_text()
        self.assertRegex(script, r"(?m)^\s*export GOW3_BACKGROUND_WARMUP=0\s*$")

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
