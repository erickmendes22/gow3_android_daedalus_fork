#!/usr/bin/env python3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ports/sotc/android"))
from stage_wave64_absent_lanes import OLD, NEW, patch_wave64_absent_lanes

class TestWave64(unittest.TestCase):
    def test_shader_logic(self):
        self.assertIn("profile.subgroup_size == 64", OLD)
        self.assertIn("FoldAbsentLaneReads(program, num_threads)", NEW)
        self.assertIn("ReductionIdentity(inst.Arg(0))", NEW)
        self.assertIn("if (fold_absent && num_threads < 64)", NEW)
        self.assertIn('SOTC_WAVE64_ABSENT_LANES', NEW)
    def test_patch_and_shader_cache(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            a = root / "shadps4/shader_recompiler/ir/passes/lower_wave64_pass.cpp"
            b = root / "shadps4/video_core/renderer_vulkan/vk_pipeline_serialization.cpp"
            a.parent.mkdir(parents=True)
            b.parent.mkdir(parents=True)
            a.write_text("#include <cstdint>\n" + OLD)
            b.write_text("static const u32 ShaderBinaryVersion = Shader::LodFeedbackEnabled() ? 38u : 135u;\n")
            patch_wave64_absent_lanes(root)
            self.assertIn("FoldAbsentLaneReads(program, num_threads)", a.read_text())
            self.assertIn("39u : 136u;", b.read_text())
            with self.assertRaises(ValueError):
                patch_wave64_absent_lanes(root)

if __name__ == "__main__":
    unittest.main()
