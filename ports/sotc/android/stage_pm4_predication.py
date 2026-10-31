#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Integrate REAL PM4 predication / ZPASS queries from shadPS4 into SotC Android.

This stage modifies only the isolated copied SotC Vulkan tree, never Bachata,
GoW3 or the SotC PC upstream. Original GPL-2.0 sources from shadPS4 commit
3559530df5aec4067a95912af13ef14896b65ada are in predication_upstream/.
Abort on upstream changes instead of guessing/replacing unrelated blocks.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENDOR = ROOT / "predication_upstream"

def replace_once(src: str, old: str, new: str, label: str) -> str:
    n = src.count(old)
    if n != 1:
        raise ValueError(f"predication staging: {label}: expected one anchor, found {n}")
    return src.replace(old, new, 1)

def patch(gpu: Path):
    core = gpu / "shadps4/video_core"
    vk = core / "renderer_vulkan"
    host = core / "host_shaders"
    # Original algorithm stays intact: query pool, GPU query reduction,
    # VK_EXT_conditional_rendering, asynchronous guest ZPASS writeback.
    (vk / "vk_predication.h").write_text((VENDOR / "vk_predication.h").read_text())
    (host / "occlusion_predicate.comp").write_text((VENDOR / "occlusion_predicate.comp").read_text())
    s = (VENDOR / "vk_predication.cpp").read_text()
    s = replace_once(s,
        'Compile(HostShaders::OCCLUSION_PREDICATE_COMP, vk::ShaderStageFlagBits::eCompute, device)',
        'CompileSPV(HostShaders::OCCLUSION_PREDICATE_COMP, device)',
        "SotC shader utility signature")
    s = replace_once(s,
        '''      predicate_buffer{instance_,
                       scheduler_,
                       VideoCore::MemoryUsage::DeviceLocal,
                       0,
                       PredicateBufferUsage(instance_),
                       NumPredicateSlots * sizeof(u32)},
      counter_scratch{instance_,
                      scheduler_,
                      VideoCore::MemoryUsage::DeviceLocal,
                      0,
                      vk::BufferUsageFlagBits::eStorageBuffer |
                          vk::BufferUsageFlagBits::eTransferDst,
                      NumScratchQwords * sizeof(u64)}''',
        '''      predicate_buffer{instance_, 0, NumPredicateSlots * sizeof(u32),
                       VideoCore::MemoryType::DeviceLocal, "SotC Predicate Buffer",
                       supported ? vk::BufferUsageFlagBits::eConditionalRenderingEXT
                                 : vk::BufferUsageFlags{}},
      counter_scratch{instance_, 0, NumScratchQwords * sizeof(u64),
                      VideoCore::MemoryType::DeviceLocal, "SotC Predicate Counter Scratch"}''',
        "SotC buffer constructor and conditional usage")
    s = replace_once(s,
        '''    if (const auto barrier = buffer->GetBarrier(vk::AccessFlagBits2::eTransferRead,
                                                vk::PipelineStageFlagBits2::eAllTransfer)) {
        RecordBufferBarrier(cmdbuf, *barrier);
    }''',
        '''    // SotC's Buffer does not expose the newer shadPS4 tracked barrier API.
    // Synchronize ALL earlier buffer writers before copying the predicate.
    RecordBufferBarrier(cmdbuf,
        MakeBufferBarrier(buffer->Handle(), vk::PipelineStageFlagBits2::eAllCommands,
                          vk::AccessFlagBits2::eMemoryWrite,
                          vk::PipelineStageFlagBits2::eAllTransfer,
                          vk::AccessFlagBits2::eTransferRead, offset, width));''',
        "SotC buffer access barrier")
    # Cond-rendering calls use extension commands NOT already wrapped by the
    # SotC deferred recorder. Android must use SOTC_RECORD_THREAD=0 unless
    # vk_recorder supplies deep-copy thunks for both extension commands.
    (vk / "vk_predication.cpp").write_text(s)

    path = gpu / "CMakeLists.txt"
    s = path.read_text()
    s = replace_once(s,
        "add_host_shader(fault_buffer_process.comp fault_buffer_process_comp)",
        "add_host_shader(fault_buffer_process.comp fault_buffer_process_comp)\n"
        "add_host_shader(occlusion_predicate.comp occlusion_predicate_comp)",
        "compile predication reduction shader")
    path.write_text(s)

    path = core / "buffer_cache/buffer.h"
    s = path.read_text()
    s = replace_once(s,
        'MemoryType mem_type, std::string_view debug_name = "");',
        'MemoryType mem_type, std::string_view debug_name = "",\n'
        '                    vk::BufferUsageFlags extra_usage = {});',
        "extra buffer usage overload")
    path.write_text(s)

    path = core / "buffer_cache/buffer.cpp"
    s = path.read_text()
    s = replace_once(s,
        '''Buffer::Buffer(const Vulkan::Instance& instance, VAddr cpu_addr_, u64 size_bytes_,
               MemoryType mem_type_, std::string_view debug_name)''',
        '''Buffer::Buffer(const Vulkan::Instance& instance, VAddr cpu_addr_, u64 size_bytes_,
               MemoryType mem_type_, std::string_view debug_name,
               vk::BufferUsageFlags extra_usage)''',
        "buffer constructor")
    s = replace_once(s, ".usage = AllFlags,", ".usage = AllFlags | extra_usage,", "conditional buffer usage")
    path.write_text(s)

    path = vk / "vk_instance.h"
    s = path.read_text()
    s = replace_once(s,
        "    /// Returns true if VK_KHR_maintenance8 is supported",
        '''    bool IsConditionalRenderingSupported() const {
        return conditional_rendering;
    }

    bool IsHostQueryResetSupported() const {
        return vk12_features.hostQueryReset;
    }

    /// Returns true if VK_KHR_maintenance8 is supported''',
        "Vulkan support accessors")
    s = replace_once(s, "    bool maintenance_8{};",
        "    bool maintenance_8{};\n    bool conditional_rendering{};",
        "Vulkan conditional feature field")
    path.write_text(s)

    path = vk / "vk_instance.cpp"
    s = path.read_text()
    s = replace_once(s,
        "        vk::PhysicalDeviceFaultFeaturesEXT>();",
        "        vk::PhysicalDeviceFaultFeaturesEXT,\n"
        "        vk::PhysicalDeviceConditionalRenderingFeaturesEXT>();",
        "query conditional rendering physical device feature")
    s = replace_once(s,
        "    maintenance_8 = add_extension(VK_KHR_MAINTENANCE_8_EXTENSION_NAME);",
        '''    maintenance_8 = add_extension(VK_KHR_MAINTENANCE_8_EXTENSION_NAME);
    conditional_rendering = add_extension(VK_EXT_CONDITIONAL_RENDERING_EXTENSION_NAME);
    conditional_rendering = conditional_rendering &&
        bool(feature_chain.get<vk::PhysicalDeviceConditionalRenderingFeaturesEXT>()
                 .conditionalRendering);
    std::fprintf(stderr, "SotC PM4 predication: conditional_rendering=%d host_query_reset=%d\\n",
                 int(conditional_rendering),
                 int(feature_chain.get<vk::PhysicalDeviceVulkan12Features>().hostQueryReset));''',
        "enable VK_EXT_conditional_rendering if supported")
    s = replace_once(s,
        '''        vk::PhysicalDeviceShaderClockFeaturesKHR{
            .shaderSubgroupClock = shader_clock_features.shaderSubgroupClock,
        },
    };''',
        '''        vk::PhysicalDeviceShaderClockFeaturesKHR{
            .shaderSubgroupClock = shader_clock_features.shaderSubgroupClock,
        },
        vk::PhysicalDeviceConditionalRenderingFeaturesEXT{
            .conditionalRendering = vk::True,
        },
    };''',
        "device feature chain")
    s = replace_once(s,
        '''    if (!custom_border_color) {
        device_chain.unlink<vk::PhysicalDeviceCustomBorderColorFeaturesEXT>();
    }''',
        '''    if (!conditional_rendering) {
        device_chain.unlink<vk::PhysicalDeviceConditionalRenderingFeaturesEXT>();
    }
    if (!custom_border_color) {
        device_chain.unlink<vk::PhysicalDeviceCustomBorderColorFeaturesEXT>();
    }''',
        "conditional feature omission")
    path.write_text(s)
    print("SotC predication: staged GPU query/compute/extension/conditional-buffer plumbing")

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--gpu", type=Path, required=True)
    patch(p.parse_args().gpu)
