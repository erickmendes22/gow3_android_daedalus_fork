#!/usr/bin/env python3
"""Android render mode must not drop visible geometry while compiling shaders."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "ports/sotc/android/run-sotc-bionic.sh"
SRT = ROOT / "ports/sotc/android/stage_srt_arm64.py"

class SotcRenderCompletenessTest(unittest.TestCase):
    def test_android_async_graphics_is_off_by_default_and_opt_in(self):
        text = LAUNCHER.read_text()
        # Controlled graphics compilation is reversible, while the two
        # other async mechanisms remain OFF for an isolated comparison.
        self.assertIn("export SOTC_ASYNC_SHADERS=${SOTC_ASYNC_SHADERS:-0}", text)
        self.assertIn("export SOTC_ASYNC_TRANSLATE=0", text)
        self.assertIn("export SOTC_ASYNC_PRELOAD=0", text)
        self.assertIn("temporary missing geometry", text)
        self.assertLess(text.index("export SOTC_ASYNC_SHADERS="), text.index('exec "$@"'))

    def test_async_first_use_draws_are_never_discarded(self):
        text = LAUNCHER.read_text()
        patch = (ROOT / "ports/sotc/android/stage_sotc_complete_draws.py").read_text()
        stage = (ROOT / "ports/sotc/android/stage_renderer.py").read_text()
        self.assertIn("export SOTC_NO_DROPPED_DRAWS=1", text)
        self.assertIn("patch_sotc_complete_draws(out)", stage)
        # These are the actual AjncSystem SotC paths, NOT GoW3's PipelineCache.
        self.assertIn("async_translate_ok = !SotcRequireCompleteDraws()", patch)
        self.assertIn("if (queued && liverpool->regs.num_indices > 6 &&", patch)
        self.assertIn("!SotcRequireCompleteDraws()) {", patch)
        self.assertIn("QueueAsyncPipeline(pipeline_hash)", patch)
        self.assertIn("SOTC_STAGE_SPEC_MEMO", patch)
        self.assertLess(text.index("export SOTC_NO_DROPPED_DRAWS=1"),
                        text.index('exec "$@"'))

    def test_no_zero_filled_texture_placeholders_on_android(self):
        text = LAUNCHER.read_text()
        self.assertIn("export SOTC_UPLOAD_BUDGET_MB=0", text)
        self.assertLess(text.index("export SOTC_UPLOAD_BUDGET_MB=0"), text.index('exec "$@"'))
        self.assertIn("zero-fill upload deferral disabled", text)
        self.assertIn("export SOTC_RB_ASYNC=${SOTC_RB_ASYNC:-0}", text)

    def test_real_texture_lod_streaming_starts_high_stable(self):
        text = LAUNCHER.read_text()
        # Verified in the 0.1.15 Android log: with linger 0, the renderer
        # reported "texture level off" (no fine mip streaming).
        self.assertIn('export SOTC_LOD_LINGER=${SOTC_LOD_LINGER:-1}', text)
        self.assertIn('export SOTC_LOD_LEVEL=${SOTC_LOD_LEVEL:-2}', text)
        self.assertIn('export SOTC_LOD_POOL_LOW=${SOTC_LOD_POOL_LOW:-8}', text)
        self.assertIn("SotC texture streaming: high/stable", text)
        self.assertLess(text.index('export SOTC_LOD_LINGER='), text.index('exec "$@"'))

    def test_dynamic_srt_offset_remains_shader_owned(self):
        text = SRT.read_text()
        self.assertIn("NeedsShaderDynamicOffset(src_off_dw) ||", text)
        self.assertIn("return (inst->Flags<u32>() & ReadConstDynamicWindowFlag) != 0;", text)
        self.assertIn("OpCopyWindow", text)

if __name__ == "__main__":
    unittest.main()
