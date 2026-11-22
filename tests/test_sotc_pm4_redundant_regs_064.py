#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""PM4 exact duplicate elimination: no guest draw or context-hint elision."""
import tempfile
import unittest
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"ports/sotc/android"))
from stage_sotc_pm4_redundant_regs_064 import patch

CONFIG='''                std::memcpy(&regs.reg_array[reg_addr], payload, (count - 1) * sizeof(u32));
                MarkRegs(reg_addr, count - 1);'''
SHADER='''                    std::memcpy(&regs.reg_array[Regs::ShRegWordOffset + set_data->reg_offset],
                                header + 2, set_size);
                    MarkRegs(Regs::ShRegWordOffset + set_data->reg_offset,
                             static_cast<u32>(set_size / 4));'''
UCONFIG='''                std::memcpy(&regs.reg_array[Regs::UconfigRegWordOffset + set_data->reg_offset],
                            header + 2, (count - 1) * sizeof(u32));
                MarkRegs(Regs::UconfigRegWordOffset + set_data->reg_offset, count - 1);'''
FIXTURE='''void Liverpool::ProcessCommands() {
}
void Liverpool::Parse() {
    case PM4ItOpcode::SetConfigReg: {
'''+CONFIG+'''
    }
    case PM4ItOpcode::SetContextReg: {
'''+CONFIG+'''
    last_cb_extent[col_buf_id].raw = payload[nop_offset + 1];
    last_db_extent.raw = payload[21];
    }
    case PM4ItOpcode::SetShReg: {
    mapped_queues[GfxQueueId].cs_state;
'''+SHADER+'''
    }
    case PM4ItOpcode::SetUconfigReg: {
'''+UCONFIG+'''
    }
    regs.SetDefaults();
    MarkRegs(0, Regs::NumRegs);
}
'''

class Pm4RedundantRegTests(unittest.TestCase):
    def make_src(self,root,broken=False):
        p=root/"shadps4/video_core/amdgpu/liverpool.cpp"
        p.parent.mkdir(parents=True)
        p.write_text(FIXTURE.replace(UCONFIG, "BROKEN") if broken else FIXTURE)
        return p

    def test_four_register_classes_and_safe_context_side_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            source=self.make_src(base)
            patch(base)
            s=source.read_text()
            self.assertIn("SOTC PM4 SAME-REG:",s)
            self.assertEqual(s.count("SotcRedundantRegBlock("),5)
            self.assertEqual(s.count("if (!SotcRedundantRegBlock("),4)
            self.assertIn("std::memcmp(dst, src, words * sizeof(u32)) == 0",s)
            self.assertIn("if (probes == 8192 && duplicates * 4 < probes) active = false;",s)
            self.assertIn("last_cb_extent[col_buf_id].raw = payload[nop_offset + 1]",s)
            self.assertIn("last_db_extent.raw = payload[21]",s)
            self.assertIn("regs.SetDefaults();",s)
            self.assertIn("MarkRegs(0, Regs::NumRegs);",s)
            self.assertIn("mapped_queues[GfxQueueId].cs_state",s)
            with self.assertRaises(ValueError):
                patch(base)

    def test_missing_src_block_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            self.make_src(base, broken=True)
            with self.assertRaises(ValueError):
                patch(base)

    def test_stage_and_zero_mode_no_clear(self):
        staged=(ROOT/"ports/sotc/android/stage_renderer.py").read_text()
        self.assertIn("patch_pm4_redundant(out)",staged)
        self.assertNotIn("patch_indirect_empty",staged)
        sun=(ROOT/"ports/sotc/android/stage_sotc_sun_shadow_cascades_059.py").read_text()
        self.assertIn("if (keep == 0) {",sun)
        self.assertLess(sun.index("if (keep == 0) {"),
                        sun.index("scheduler.EndRendering();"))

if __name__=="__main__":
    unittest.main()
