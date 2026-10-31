// SPDX-License-Identifier: GPL-2.0-or-later
// Generates the real SotC geometry stage using the staged renderer's emitter.
// This test is designed to run without the PS4 game or Vulkan device.
#include <filesystem>
#include <fstream>
#include <cstdio>
#include <vector>
#include "shader_recompiler/info.h"
#include "shader_recompiler/runtime_info.h"
#include "shader_recompiler/backend/spirv/emit_spirv_quad_rect.h"

int main(int argc, char** argv) {
    if (argc != 2) return 2;
    Shader::Info info{};
    info.hw_stage = Shader::HwStage::Fragment;
    info.sw_stage = Shader::SwStage::Fragment;
    Shader::RuntimeInfo runtime{};
    runtime.Initialize(info.hw_stage, info.sw_stage);
    auto& fs = runtime.hw.fs;
    fs.num_inputs = 3;
    fs.clip_distance_emulation = true;
    fs.inputs[0] = {.param_index=0, .is_default=false, .is_flat=true};
    fs.inputs[1] = {.param_index=2, .is_default=false, .is_flat=false};
    fs.inputs[2] = {.param_index=0, .is_default=true, .is_flat=false};
    info.fs_interpolation[0].primary = Shader::Qualifier::PerVertex;
    info.fs_interpolation[1].primary = Shader::Qualifier::Smooth;

    const auto compiled=Shader::Backend::SPIRV::EmitBarycentricGeometryShader(fs,info);
    if(compiled.empty()) return 3;
    const std::filesystem::path out=argv[1];
    std::filesystem::create_directories(out.parent_path());
    std::ofstream file(out, std::ios::binary);
    file.write(reinterpret_cast<const char*>(compiled.data()),
               std::streamsize(compiled.size()*sizeof(u32)));
    if(!file) return 4;
    std::fprintf(stderr,"SotC actual GS emitted %zu SPIR-V words\n",compiled.size());
    return 0;
}
