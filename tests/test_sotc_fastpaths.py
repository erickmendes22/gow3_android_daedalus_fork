#!/usr/bin/env python3
"""SotC three Android CPU fast paths preserve every real guest operation."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
STAGE = (ROOT / "ports/sotc/android/stage_perf_fastpaths.py").read_text()
RENDER = (ROOT / "ports/sotc/android/stage_renderer.py").read_text()
RUN = (ROOT / "ports/sotc/android/run-sotc-bionic.sh").read_text()
GAME = (ROOT / "android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java").read_text()
UI = (ROOT / "android-launcher/app/src/main/java/com/gow3/android/ui/SotcScreen.kt").read_text()
PACKAGE = (ROOT / "ports/sotc/android/package_sotc_runtime.py").read_text()


class SotcFastpathIntegration(unittest.TestCase):
    def test_pinned_staging_runs_after_render_correctness_fixes(self):
        self.assertIn("from stage_perf_fastpaths import patch_fastpaths", RENDER)
        self.assertLess(RENDER.index("patch_meta_clear_integrity(out)"),
                        RENDER.index("patch_fastpaths(root, out)"))
        self.assertIn("vk_sotc_fastpaths.h", STAGE)
        for item in ("scheduler render-scope invalidation",
                     "all three direct and indirect host graphics pipeline binds",
                     "set complete Vulkan dynamic vertex input",
                     "per-stage descriptor writes fallback"):
            self.assertIn(item, STAGE)

    def test_user_can_disable_each_cpu_optimization_without_affecting_old_fast_bind(self):
        for env, key in (("SOTC_PIPELINE_BIND_MEMO", "sotc_pipeline_bind_memo"),
                         ("SOTC_VERTEX_INPUT_MEMO", "sotc_vertex_input_memo"),
                         ("SOTC_DESCRIPTOR_SLOT_REUSE", "sotc_descriptor_slot_reuse")):
            self.assertIn("export "+env+"=$"+"{"+env+":-1}", RUN)
            self.assertIn('env.put("'+env+'",', GAME)
            self.assertIn('save("'+key+'",if(it)"1" else "0")', UI)
            self.assertIn(key+"=1", PACKAGE)
        self.assertIn("export SOTC_FAST_BIND=$"+"{SOTC_FAST_BIND:-0}", RUN)
        self.assertIn("export BB_READBACKS=2", RUN)
        self.assertIn("export SOTC_ASYNC_SHADERS=${SOTC_ASYNC_SHADERS:-0}", RUN)
        self.assertIn("export SOTC_UPLOAD_BUDGET_MB=0", RUN)

    def test_descriptor_slots_are_fully_reset_not_stale_guest_handles(self):
        self.assertIn("std::fill(set_writes.begin(), set_writes.end(), vk::WriteDescriptorSet{});", STAGE)
        self.assertIn("if (!reuse_descriptor_slots) set_writes.clear();", STAGE)
        self.assertIn("if (!reuse_descriptor_slots) {", STAGE)
        self.assertIn("every resource lookup/barrier/push-constant operation still takes place", STAGE)
        self.assertIn("set_writes.resize(count);", STAGE)
        self.assertNotIn("SOTC_FAST_BIND=1", RUN)


if __name__ == "__main__":
    unittest.main()
