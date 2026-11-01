#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""SotC Android profiling gates: actual CPU clocks, optional instrumentation."""
from pathlib import Path
import importlib.util
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / 'ports/sotc/android/stage_sotc_perf_profile.py'
STAGE = ROOT / 'ports/sotc/android/stage_renderer.py'
RUN = ROOT / 'ports/sotc/android/run-sotc-bionic.sh'
GAME = ROOT / 'android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java'
UI = ROOT / 'android-launcher/app/src/main/java/com/gow3/android/ui/SotcScreen.kt'
PACKAGE = ROOT / 'ports/sotc/android/package_sotc_runtime.py'
UPSTREAM = ROOT / 'upstream-sotc/gpu/shadps4/video_core/sotc_stats.cpp'

spec = importlib.util.spec_from_file_location("stage_sotc_perf_profile_test",PROFILE)
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)

FALLBACK = """#else
void RegisterSplitThread(SplitThread) {}

uint64_t SplitThreadCycles(SplitThread) {
    return 0;
}

uint64_t SplitProcessFaults() {
    return 0;
}
#endif"""


class SotcFrameProfileTest(unittest.TestCase):
    def test_real_cpu_clocks_not_zero_in_android(self):
        source = PROFILE.read_text()
        for part in ("pthread_getcpuclockid(pthread_self(), &id)",
                     "clock_gettime(cpu_clock_id[which].load",
                     "cntfrq_el0", "__uint128_t(ns)",
                     "getrusage(RUSAGE_SELF, &usage)",
                     "std::memory_order_acquire",
                     "if (!kDrawSplit) return 0;"):
            self.assertIn(part, source)
        self.assertIn("from stage_sotc_perf_profile import patch_profile", STAGE.read_text())
        mock = '#include "video_core/sotc_stats.h"\n' + FALLBACK
        with tempfile.TemporaryDirectory() as d:
            gpu = Path(d)
            (gpu/'shadps4/video_core').mkdir(parents=True)
            target = gpu/'shadps4/video_core/sotc_stats.cpp'
            target.write_text(mock)
            profile.patch_profile(gpu)
            out = target.read_text()
            self.assertIn("#elif defined(__ANDROID__)", out)
            self.assertIn("pthread_getcpuclockid", out)
            self.assertIn("getrusage(RUSAGE_SELF", out)
            with self.assertRaises(ValueError):
                profile.patch_profile(gpu)

    @unittest.skipUnless(UPSTREAM.exists(), "requires pinned upstream checkout")
    def test_exact_source_compatible_with_pinned_renderer(self):
        with tempfile.TemporaryDirectory() as d:
            gpu=Path(d)
            (gpu/'shadps4/video_core').mkdir(parents=True)
            src=gpu/'shadps4/video_core/sotc_stats.cpp'
            src.write_bytes(UPSTREAM.read_bytes())
            profile.patch_profile(gpu)
            compiled=src.read_text()
            self.assertIn("uint64_t SplitThreadCycles(SplitThread which)",compiled)
            self.assertIn("uint64_t SplitProcessFaults()", compiled)

    def test_profiler_is_opt_in_without_changing_vulkan_controls(self):
        shell=RUN.read_text()
        java=GAME.read_text()
        ui=UI.read_text()
        pkg=PACKAGE.read_text()
        self.assertIn('if [ "$'+'{SOTC_PERF_PROFILE:-0}" = "1" ]; then',shell)
        self.assertIn("export SOTC_FPS=1",shell)
        self.assertIn("export SOTC_DRAW_SPLIT=1",shell)
        self.assertIn("unset SOTC_FPS SOTC_DRAW_SPLIT SOTC_CMD_STATS",shell)
        self.assertIn('env.put("SOTC_PERF_PROFILE",',java)
        self.assertIn('save("sotc_perf_profile",if(it)"1" else "0")',ui)
        self.assertIn("sotc_perf_profile=0",pkg)
        for keep in ('export BB_READBACKS=${BB_READBACKS:-2}',
                     'export SOTC_UPLOAD_BUDGET_MB=0',
                     'export SOTC_ASYNC_TRANSLATE=0'):
            self.assertIn(keep,shell)
        self.assertNotIn('export SOTC_FPS=0',shell)
        self.assertNotIn('export SOTC_DRAW_SPLIT=0',shell)


if __name__ == "__main__":
    unittest.main()
