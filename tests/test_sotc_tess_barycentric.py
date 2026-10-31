#!/usr/bin/env python3
"""Regression: Adreno fragment inputs must have a producer after guest TES."""
import ast
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "ports/sotc/android/stage_renderer.py"
PATCH = ROOT / "ports/sotc/android/stage_adreno_tess_barycentric.py"
sys.path.insert(0, str(PATCH.parent))
from stage_adreno_tess_barycentric import patch_adreno_tess_barycentric


def original_gate():
    # Read the exact upstream gate defined in the source patch. Keeping this
    # fixture derived from our staging script avoids a fragile manually copied
    # snippet that would not match after upstream changes.
    tree = ast.parse(PATCH.read_text())
    fun = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
               and n.name == "patch_adreno_tess_barycentric")
    before = next(n.value.value for n in fun.body if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == "before" for t in n.targets))
    return before


class BarycentricTessProducer(unittest.TestCase):
    def test_upstream_gate_repaired_without_touching_barycentric_math(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "shadps4/video_core/renderer_vulkan/vk_graphics_pipeline.cpp"
            path.parent.mkdir(parents=True)
            # Minimal source with all required downstream shader producer symbols.
            path.write_text(original_gate() + """
        Shader::Backend::SPIRV::NeedsBarycentricGs(fs_runtime, *fs_stage_info);
        sdata.gs = Shader::Backend::SPIRV::EmitBarycentricGeometryShader(fs_runtime,
                                                                          *fs_stage_info);
        shader_stages.emplace_back(vk::PipelineShaderStageCreateInfo{
            .stage = vk::ShaderStageFlagBits::eGeometry,
            .module = CompileSPV(sdata.gs, instance.GetDevice()),
        });
""")
            patch_adreno_tess_barycentric(Path(tmp))
            fixed = path.read_text()
            self.assertIn("tessellated_triangles", fixed)
            self.assertIn("AmdGpu::TessellationType::Triangle", fixed)
            self.assertIn("AmdGpu::TessellationType::Quad", fixed)
            self.assertNotIn("!infos[u32(Shader::SwStage::TessellationEval)]", fixed)
            self.assertIn("!infos[u32(Shader::SwStage::Geometry)]", fixed)
            self.assertIn("!has_guest_tes || tessellated_triangles", fixed)
            self.assertIn("sdata.gs = Shader::Backend::SPIRV::EmitBarycentricGeometryShader", fixed)
            self.assertIn("CompileSPV(sdata.gs, instance.GetDevice())", fixed)
            with self.assertRaises(ValueError):
                patch_adreno_tess_barycentric(Path(tmp))

    def test_pipeline_stage_is_after_position_only_gs_patch(self):
        s = STAGE.read_text()
        self.assertIn("patch_adreno_tess_barycentric(out)", s)
        self.assertLess(s.index("patch_adreno_gs_position(out)"),
                        s.index("patch_adreno_tess_barycentric(out)"))

    def test_structural_explanation_matches_unconnected_fs_inputs(self):
        s = PATCH.read_text()
        self.assertIn("without any producer", s)
        self.assertIn("profile.barycentric_via_gs", s)
        self.assertIn("tess_type == AmdGpu::TessellationType::Quad", s)


if __name__ == "__main__":
    unittest.main()
