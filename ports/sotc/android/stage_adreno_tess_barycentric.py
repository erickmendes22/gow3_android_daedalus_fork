#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""SotC Android: attach the existing barycentric GS after guest triangle/quad tessellation.

The fragment compiler sees profile.barycentric_via_gs globally on Adreno and
generates reads of the GS-owned input locations for *all* qualifying shaders.
The PC pipeline builder only inserts that GS for regular triangles, explicitly
excluding every guest TES, even when TES emits triangles. Vulkan allows the
unwritten fragment inputs to be undefined; they appear as missing material,
invalid lighting or stretched interpolants. Preserve the existing generated GS
and its validated Position-only interface; make its producer match the shader.

This stage does not alter guest x86 code, shader math, Mali, or the PC port.
"""
from pathlib import Path


def patch_adreno_tess_barycentric(gpu: Path) -> None:
    path = gpu / "shadps4/video_core/renderer_vulkan/vk_graphics_pipeline.cpp"
    text = path.read_text()
    before = '''    // sotc: Profile::barycentric_via_gs: the geometry shader that hands the pixel shader its
    // per-vertex inputs and barycentrics, on triangles without a guest geometry/tess stage.
    const Shader::Info* fs_stage_info = infos[u32(Shader::SwStage::Fragment)];
    const bool triangles = topology == vk::PrimitiveTopology::eTriangleList ||
                           topology == vk::PrimitiveTopology::eTriangleStrip ||
                           topology == vk::PrimitiveTopology::eTriangleFan || is_rect_list ||
                           is_quad_list;
    // Preloaded pipelines take it from the cache: the interpolation data it needs is not stored.
    if (!preloading && profile.barycentric_via_gs && fs_stage_info && triangles &&
        !infos[u32(Shader::SwStage::Geometry)] &&
        !infos[u32(Shader::SwStage::TessellationEval)]) {'''
    after = '''    // Adreno: the fragment shader is lowered with barycentric_via_gs for
    // EVERY pipeline. If a guest tessellation-evaluation shader is present,
    // its outputs are still the immediate input to this barycentric GS. The
    // previous no-TES guard left the fragment's GS-owned input locations
    // without any producer, breaking materials/depth/fog on tessellated land.
    // Vulkan tessellation domains Triangle and Quad both generate triangles;
    // Isoline generates lines, which this triangle GS must never consume.
    const Shader::Info* fs_stage_info = infos[u32(Shader::SwStage::Fragment)];
    const u32 tes_stage = u32(Shader::SwStage::TessellationEval);
    const bool has_guest_tes = infos[tes_stage] != nullptr;
    const bool tessellated_triangles = has_guest_tes &&
        (runtime_infos[tes_stage].sw.tes.tess_type == AmdGpu::TessellationType::Triangle ||
         runtime_infos[tes_stage].sw.tes.tess_type == AmdGpu::TessellationType::Quad);
    const bool triangles = topology == vk::PrimitiveTopology::eTriangleList ||
                           topology == vk::PrimitiveTopology::eTriangleStrip ||
                           topology == vk::PrimitiveTopology::eTriangleFan || is_rect_list ||
                           is_quad_list || tessellated_triangles;
    // Existing cached pipelines keep their saved GS; phi7 uses a fresh
    // shader/pipeline cache because the earlier versions omitted this stage.
    if (!preloading && profile.barycentric_via_gs && fs_stage_info && triangles &&
        !infos[u32(Shader::SwStage::Geometry)] &&
        (!has_guest_tes || tessellated_triangles)) {'''
    if text.count(before) != 1:
        raise ValueError("SotC TES/GS: expected exact uncorrected pipeline producer gate")
    text = text.replace(before, after, 1)
    for required in (
        "Shader::Backend::SPIRV::NeedsBarycentricGs(fs_runtime, *fs_stage_info)",
        "Shader::Backend::SPIRV::EmitBarycentricGeometryShader(fs_runtime,",
        "sdata.gs =",
        "CompileSPV(sdata.gs, instance.GetDevice())",
        "shader_stages.emplace_back(vk::PipelineShaderStageCreateInfo{",
    ):
        if required not in text:
            raise ValueError("SotC TES/GS: missing upstream producer " + required)
    path.write_text(text)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--gpu", type=Path, required=True)
    patch_adreno_tess_barycentric(p.parse_args().gpu)
