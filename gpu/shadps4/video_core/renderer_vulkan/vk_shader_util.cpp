// SPDX-FileCopyrightText: Copyright 2024 shadPS4 Emulator Project
// SPDX-License-Identifier: GPL-2.0-or-later

#include "common/assert.h"
#include "video_core/renderer_vulkan/vk_shader_util.h"
#include "video_core/renderer_vulkan/vk_mali_early_z.h"
#include <cstdlib>
#include <vector>

namespace Vulkan {

vk::ShaderModule CompileSPV(std::span<const u32> code, vk::Device device) {
    // The renderer routinely loads SPIR-V from the existing shader cache.
    // Apply this safe, optional mobile optimization *after* cache loading so
    // its activation never invalidates the user's 1300+ compiled programs.
    // Only opaque, side-effect-free fragment programs receive EarlyFragmentTests.
    // This can reject hidden fragments before expensive texture/ALU work on
    // tile-based Mali GPUs; driver may independently choose early Z anyway.
    std::vector<u32> early_z_code;
#ifdef __ANDROID__
    static const bool mali_early_z = [] {
        const char* option = std::getenv("GOW3_MALI_GPU_EARLY_Z");
        return std::getenv("GOW3_MALI_CPU_PRESENT") != nullptr &&
               (!option || option[0] != '0');
    }();
    if (mali_early_z && MaliEarlyZ::Transform(code, early_z_code)) {
        code = early_z_code;
    }
#endif
    const vk::ShaderModuleCreateInfo shader_info = {
        .codeSize = code.size() * sizeof(u32),
        .pCode = code.data(),
    };

    auto [module_result, module] = device.createShaderModule(shader_info);
    ASSERT_MSG(module_result == vk::Result::eSuccess, "Failed to compile SPIR-V shader: {}",
               vk::to_string(module_result));
    return module;
}

} // namespace Vulkan
