"""Guard PanVK stable memory watermarks and clarify guest layout aliases."""
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]
TEX = (ROOT / 'gpu/shadps4/video_core/texture_cache/texture_cache.cpp').read_text()
SH = (ROOT / 'tools/android/bionic/run-bionic.sh').read_text()


class MaliBudgetAndLayoutTests(unittest.TestCase):
    def test_pressure_is_opt_in_not_new_default(self):
        self.assertIn('GOW3_MALI_GC_PRESSURE_PCT=${GOW3_MALI_GC_PRESSURE_PCT:-85}', SH)
        self.assertIn('std::getenv("GOW3_MALI_GC_PRESSURE_PCT")', TEX)
        self.assertIn('std::getenv("GOW3_MALI_CPU_PRESENT")', TEX)
        self.assertIn('parsed < 85 || parsed > 90', TEX)
        self.assertIn('pressure_gc_memory = budget / 100 * mali_pressure_pct;', TEX)
        self.assertIn('critical_gc_memory = budget / 100 * 95;', TEX)

    def test_guard_stays_protective_and_reports_real_format(self):
        self.assertIn('GOW3_TEXTURE_OVERLAP_LAYOUT_REJECT source=port_alias_guard', TEX)
        self.assertIn('GOW3_TEXTURE_LAYOUT_REJECT source=port_exact_match_guard', TEX)
        self.assertIn('cached_format=%s requested_format=%s', TEX)
        self.assertIn('vk::to_string(b.pixel_format).c_str()', TEX)
        self.assertIn('vk::to_string(a.pixel_format).c_str()', TEX)
        self.assertIn('if (safe_to_delete) FreeImage(cache_image_id)', TEX)
        self.assertIn('a.pitch != b.pitch || a.tile_mode != b.tile_mode', TEX)
        self.assertIn('b.num_samples, a.num_samples', TEX)


if __name__ == '__main__':
    unittest.main()
