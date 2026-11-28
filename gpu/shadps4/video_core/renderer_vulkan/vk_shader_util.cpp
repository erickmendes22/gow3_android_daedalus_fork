// SPDX-FileCopyrightText: Copyright 2024 shadPS4 Emulator Project
// SPDX-License-Identifier: GPL-2.0-or-later

#include <cstdlib>
#include <mutex>
#include <unordered_map>
#include "common/assert.h"
#include "video_core/renderer_vulkan/vk_shader_util.h"

namespace Vulkan {
namespace {
// Only shader creation and pipeline creation touch this map, never draws.
// Reused handles are overwritten even for non-fragment modules.
std::mutex ub2_shader_mutex;
std::unordered_map<VkShaderModule, Ub2Vrs::FragmentClass> ub2_shader_classes;
}
Ub2Vrs::FragmentClass GetUb2VrsFragmentClass(vk::ShaderModule module) {
    std::scoped_lock lock{ub2_shader_mutex};
    const auto it = ub2_shader_classes.find(static_cast<VkShaderModule>(module));
    return it == ub2_shader_classes.end() ? Ub2Vrs::FragmentClass::Unknown : it->second;
}

vk::ShaderModule CompileSPV(std::span<const u32> code, vk::Device device) {
    const vk::ShaderModuleCreateInfo shader_info = {
        .codeSize = code.size() * sizeof(u32),
        .pCode = code.data(),
    };

    auto [module_result, module] = device.createShaderModule(shader_info);
    ASSERT_MSG(module_result == vk::Result::eSuccess, "Failed to compile SPIR-V shader: {}",
               vk::to_string(module_result));
#ifdef __ANDROID__
    static const bool classify = std::getenv("BB_AOT") != nullptr;
    if (classify && module) {
        const auto type = Ub2Vrs::Classify(code);
        std::scoped_lock lock{ub2_shader_mutex};
        ub2_shader_classes.insert_or_assign(static_cast<VkShaderModule>(module), type);
    }
#endif
    return module;
}

} // namespace Vulkan
