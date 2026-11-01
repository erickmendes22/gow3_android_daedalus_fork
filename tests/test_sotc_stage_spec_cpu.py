#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""0.1.29: direct source/regression validation of CP shader variant hot path."""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
STAGE=ROOT/'ports/sotc/android/stage_sotc_stage_spec_cpu.py'
RENDERER=ROOT/'ports/sotc/android/stage_renderer.py'
RUN=ROOT/'ports/sotc/android/run-sotc-bionic.sh'
UI=ROOT/'android-launcher/app/src/main/java/com/gow3/android/ui/SotcScreen.kt'
JAVA=ROOT/'android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java'
PACKAGE=ROOT/'ports/sotc/android/package_sotc_runtime.py'
UPSTREAM=ROOT/'upstream-sotc/gpu'

spec=importlib.util.spec_from_file_location('sotc_029_stage_cpu',STAGE)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

SOURCE_FILES=(
    'shadps4/video_core/amdgpu/liverpool.cpp',
    'shadps4/video_core/renderer_vulkan/vk_pipeline_cache.cpp',
    'shadps4/video_core/renderer_vulkan/vk_pipeline_cache.h',
    'shadps4/video_core/sotc_stats.h',
    'shadps4/core/libraries/videoout/driver.cpp',
)

@unittest.skipUnless((UPSTREAM/'shadps4').exists(), "Pinned SotC source tree needed")
class SotcStageSpecCpuTest(unittest.TestCase):
    def test_original_gpu_changes_are_exactly_scoped(self):
        with tempfile.TemporaryDirectory() as temp:
            gpu=Path(temp)/'gpu'
            for relative in SOURCE_FILES:
                (gpu/relative).parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(UPSTREAM/relative,gpu/relative)
            module.patch_sotc_stage_spec_cpu(gpu)
            l=(gpu/SOURCE_FILES[0]).read_text()
            c=(gpu/SOURCE_FILES[1]).read_text()
            h=(gpu/SOURCE_FILES[2]).read_text()
            d=(gpu/SOURCE_FILES[4]).read_text()
            self.assertIn('rt.flattened_ud_buf.swap(stage.flat);',l)
            self.assertIn('rt.flattened_ud_buf.assign(stage.flat.begin(), stage.flat.end());',l)
            self.assertIn('sotc_last.flat == info.FlatBuf()',c)
            self.assertIn('sotc_last.program_base == info.PgmBase()',c)
            self.assertIn('sotc_last.runtime_info == rt',c)
            self.assertIn('sotc_last.start == binding',c)
            self.assertIn('sotc_last.module_count == program->modules.size()',c)
            self.assertIn('!program->translate_in_place',c)
            self.assertIn('program->pending_specs.empty()',c)
            self.assertIn('sw_stage == SwStage::Fragment || sw_stage == SwStage::Compute',c)
            self.assertIn('info.RefreshFlatBuf();',c)
            self.assertIn('program->sotc_last_safe_spec.valid = false;',c)
            self.assertIn('stage_spec_hits.fetch_add(1, std::memory_order_relaxed)',c)
            self.assertIn('struct LastSafeSpecialization',h)
            self.assertIn('SOTC STAGE SPEC MEMO hits',d)
            # We explicitly rejected the previous APK's superficial change.
            self.assertIn('static constexpr u32 RegChunkDwords = 64;',
                          (gpu/'shadps4/video_core/amdgpu/liverpool.h').read_text()
                          if (gpu/'shadps4/video_core/amdgpu/liverpool.h').exists()
                          else (UPSTREAM/'shadps4/video_core/amdgpu/liverpool.h').read_text())
            self.assertNotIn('SotcCpSpinBudget',l)
            # Fail closed: never repatch a source whose anchors have changed.
            with self.assertRaisesRegex(ValueError,'source drift'):
                module.patch_sotc_stage_spec_cpu(gpu)

    def test_reversible_independent_runtime_controls_and_srt_fidelity(self):
        run=RUN.read_text()
        java=JAVA.read_text()
        ui=UI.read_text()
        pack=PACKAGE.read_text()
        for key,setting in [('SOTC_STAGE_SPEC_MEMO','sotc_stage_spec_memo'),
                            ('SOTC_STAGE_SNAPSHOT_SWAP','sotc_stage_snapshot_swap')]:
            self.assertIn('export '+key+'=$'+'{'+key+':-1}',run)
            self.assertIn('env.put("'+key+'",',java)
            self.assertIn('save("'+setting+'",if(it)"1" else "0")',ui)
            self.assertIn(setting+'=1',pack)
        self.assertIn('patch_sotc_stage_spec_cpu(out)',RENDERER.read_text())
        self.assertIn('export BB_READBACKS=2',run)
        self.assertIn('export SOTC_ASYNC_TRANSLATE=0',run)
        # Existing deterministic strict-sync flags must not be force-enabled.
        self.assertIn('export SOTC_RB_ASYNC=',run)
        self.assertNotIn('SotcCpSpinBudget',RENDERER.read_text())

if __name__=='__main__':
    unittest.main()
