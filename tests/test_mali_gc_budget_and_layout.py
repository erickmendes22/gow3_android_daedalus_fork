"""Guard PanVK stable memory watermarks and clarify guest layout aliases."""
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]
TEX = (ROOT / 'gpu/shadps4/video_core/texture_cache/texture_cache.cpp').read_text()
SH = (ROOT / 'tools/android/bionic/run-bionic.sh').read_text()


class MaliBudgetAndLayoutTests(unittest.TestCase):
    def test_pressure_is_opt_in_not_new_default(self):
        self.assertIn('GOW3_MALI_GC_PRESSURE_PCT=${GOW3_MALI_GC_PRESSURE_PCT:-87}', SH)
        self.assertIn('std::getenv("GOW3_MALI_GC_PRESSURE_PCT")', TEX)
        self.assertIn('std::getenv("GOW3_MALI_CPU_PRESENT")', TEX)
        self.assertIn('parsed < 85 || parsed > 90', TEX)
        self.assertIn('pressure_gc_memory = budget / 100 * mali_pressure_pct;', TEX)
        self.assertIn('critical_gc_memory = budget / 100 * 95;', TEX)

    def test_mali_early_gc_waits_for_memory_pressure_by_default(self):
        # Device ZIP 20261106-064553: 701 routine deletions despite
        # no memory-pressure reports. All 24 snapshots were below 85% of
        # their then-current VMA budget; last was 2612 / (2811 / .85) MiB.
        self.assertIn(
            'GOW3_MALI_GC_TRIGGER_PCT=${GOW3_MALI_GC_TRIGGER_PCT:-87}', SH
        )
        self.assertIn('GOW3_MALI_GC_PRESSURE_PCT=${GOW3_MALI_GC_PRESSURE_PCT:-87}', SH)
        self.assertIn('trigger_gc_memory = budget / 100 * std::min(mali_trigger_pct, mali_pressure_pct);', TEX)
        self.assertIn('if (total_used_memory < trigger_gc_memory)', TEX)
        self.assertIn('(parsed != 70 && (parsed < 75 || parsed > 90))', TEX)
        self.assertIn('critical_gc_memory = budget / 100 * 95;', TEX)
        # Device log example: new trigger waits for pressure; old 70% ran.
        budget_mib=2837 / 0.85
        used_mib=2615
        self.assertGreaterEqual(used_mib, budget_mib*0.70)
        self.assertLess(used_mib, budget_mib*0.85)

    def test_seven_eighths_gc_keeps_hard_memory_limits(self):
        budget = 2595 / 0.85
        self.assertGreater(2614, budget * 0.85)
        self.assertLess(2614, budget * 0.87)
        self.assertIn('GOW3_MALI_GC_TRIGGER_PCT=${GOW3_MALI_GC_TRIGGER_PCT:-87}', SH)
        self.assertIn('GOW3_MALI_GC_PRESSURE_PCT=${GOW3_MALI_GC_PRESSURE_PCT:-87}', SH)
        self.assertIn('critical_gc_memory = budget / 100 * 95;', TEX)
        self.assertIn('VMA_ALLOCATION_CREATE_WITHIN_BUDGET_BIT',
                      (ROOT/'gpu/shadps4/video_core/texture_cache/image.cpp').read_text())

    def test_guard_stays_protective_and_reports_real_format(self):
        self.assertIn('GOW3_TEXTURE_OVERLAP_LAYOUT_REJECT source=port_alias_guard', TEX)
        self.assertIn('GOW3_TEXTURE_LAYOUT_REJECT source=port_exact_match_guard', TEX)
        self.assertIn('cached_format=%s requested_format=%s', TEX)
        self.assertIn('vk::to_string(b.pixel_format).c_str()', TEX)
        self.assertIn('vk::to_string(a.pixel_format).c_str()', TEX)
        # The original one-line branch is now braced. Keep the actual
        # GPU-modified image guard rather than testing obsolete whitespace.
        self.assertIn('if (safe_to_delete) {\n                FreeImage(cache_image_id);', TEX)
        self.assertIn('a.pitch != b.pitch || a.tile_mode != b.tile_mode', TEX)
        self.assertIn('b.num_samples, a.num_samples', TEX)


if __name__ == '__main__':
    unittest.main()
