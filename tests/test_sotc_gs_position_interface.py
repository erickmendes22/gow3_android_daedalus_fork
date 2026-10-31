#!/usr/bin/env python3
"""Adreno GS must export a Vulkan-valid Position block without unwritten members."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PATCH=ROOT/"ports/sotc/android/stage_adreno_gs_position.py"
STAGE=ROOT/"ports/sotc/android/stage_renderer.py"
RUN=ROOT/"ports/sotc/android/run-sotc-bionic.sh"

class BarycentricGeometryPositionTest(unittest.TestCase):
    def test_position_block_contains_no_undefined_members(self):
        s=PATCH.read_text()
        self.assertIn('const Id gs_position_block{m.TypeStruct(vec4_id)};',s)
        self.assertIn('m.Decorate(gs_position_block, spv::Decoration::Block);',s)
        self.assertIn('m.MemberDecorate(gs_position_block, 0U, spv::Decoration::BuiltIn,',s)
        self.assertIn('m.MemberDecorate(gs_position_block, 0U, spv::Decoration::Invariant)',s)
        self.assertIn('m.TypeArray(gs_position_block, m.Constant(uint_id, 3U))',s)
        self.assertNotIn('m.Decorate(gl_in, spv::Decoration::BuiltIn',s)
        self.assertNotIn('gs_position_input_type',s)
        self.assertIn('m.OpStore(m.OpAccessChain(out_vec4, gl_out, index(0)), position);',s)

    def test_does_not_revert_proven_barycentrics_or_wave32(self):
        self.assertIn('patch_adreno_gs_position(out)',STAGE.read_text())
        self.assertIn('patch_adreno_barycentric_gs(out)',STAGE.read_text())
        s=RUN.read_text()
        self.assertIn('export BB_READBACKS=2',s)
        self.assertIn('export SOTC_RB_ASYNC=0',s)
        self.assertIn('gpu-user-srt-phi4-barycentric-gs-$sotc_gpu_profile',s)
        self.assertNotIn('export SOTC_ADRENO_WAVE32=0',s)

if __name__=="__main__":
    unittest.main()
