// SPDX-FileCopyrightText: Copyright 2025 shadPS4 Emulator Project
// SPDX-License-Identifier: GPL-2.0-or-later

#include <cstdio>
#include <cstdlib>
#include "common/div_ceil.h"
#include "video_core/buffer_cache/fault_result_policy.h"
#include "video_core/buffer_cache/buffer_cache.h"
#include "video_core/buffer_cache/fault_manager.h"
#include "video_core/renderer_vulkan/vk_instance.h"
#include "video_core/renderer_vulkan/vk_platform.h"
#include "video_core/renderer_vulkan/vk_scheduler.h"
#include "video_core/renderer_vulkan/vk_shader_util.h"

#include "video_core/host_shaders/fault_buffer_process_comp.h"

namespace VideoCore {

static constexpr size_t MaxPageFaults = 1024;
static constexpr size_t PageFaultAreaSize = MaxPageFaults * sizeof(u64);

FaultManager::FaultManager(const Vulkan::Instance& instance, Vulkan::Scheduler& scheduler_,
                           BufferCache& buffer_cache_, u32 sparse_pagebits, u64 sparse_num_pages_)
    : scheduler{scheduler_}, buffer_cache{buffer_cache_}, sparse_pagesize{1ULL << sparse_pagebits},
      sparse_num_pages{sparse_num_pages_}, fault_buffer_size{sparse_num_pages_ / 8},
      fault_buffer{instance, 0, fault_buffer_size, MemoryType::DeviceLocal},
      download_buffer{instance, 0, MaxPendingFaults * PageFaultAreaSize, MemoryType::HostCached} {
    const char* safe = std::getenv("GOW3_MALI_SAFE_FAULT_DRAIN");
    mali_safe_fault_drain = std::getenv("GOW3_ANDROID_PORT") &&
        instance.GetPhysicalDevice().getProperties().vendorID == 0x13B5 &&
        (!safe || safe[0] != '0');
    const auto device = instance.GetDevice();
    Vulkan::SetObjectName(device, fault_buffer.Handle(), "Fault Buffer");

    const std::array<vk::DescriptorSetLayoutBinding, 2> bindings = {{
        {
            .binding = 0,
            .descriptorType = vk::DescriptorType::eStorageBuffer,
            .descriptorCount = 1,
            .stageFlags = vk::ShaderStageFlagBits::eCompute,
        },
        {
            .binding = 1,
            .descriptorType = vk::DescriptorType::eStorageBuffer,
            .descriptorCount = 1,
            .stageFlags = vk::ShaderStageFlagBits::eCompute,
        },
    }};
    const vk::DescriptorSetLayoutCreateInfo desc_layout_ci = {
        .flags = vk::DescriptorSetLayoutCreateFlagBits::ePushDescriptorKHR,
        .bindingCount = 2,
        .pBindings = bindings.data(),
    };
    fault_process_desc_layout =
        Vulkan::Check(device.createDescriptorSetLayoutUnique(desc_layout_ci));

    const std::array<u32, 2> spec_data{sparse_pagebits, MaxPageFaults};
    const std::array<vk::SpecializationMapEntry, 2> spec_entries{{
        {0, 0, sizeof(u32)},
        {1, sizeof(u32), sizeof(u32)},
    }};
    const vk::SpecializationInfo specialization{
        .mapEntryCount = static_cast<u32>(spec_entries.size()),
        .pMapEntries = spec_entries.data(),
        .dataSize = sizeof(spec_data),
        .pData = spec_data.data(),
    };
    const auto module = Vulkan::CompileSPV(FAULT_BUFFER_PROCESS_COMP, device);
    Vulkan::SetObjectName(device, module, "Fault Buffer Parser");

    const vk::PipelineShaderStageCreateInfo shader_ci = {
        .stage = vk::ShaderStageFlagBits::eCompute,
        .module = module,
        .pName = "main",
        .pSpecializationInfo = &specialization,
    };

    const vk::PipelineLayoutCreateInfo layout_info = {
        .setLayoutCount = 1U,
        .pSetLayouts = &(*fault_process_desc_layout),
    };
    fault_process_pipeline_layout = Vulkan::Check(device.createPipelineLayoutUnique(layout_info));

    const vk::ComputePipelineCreateInfo pipeline_info = {
        .stage = shader_ci,
        .layout = *fault_process_pipeline_layout,
    };
    fault_process_pipeline = Vulkan::Check(device.createComputePipelineUnique({}, pipeline_info));
    Vulkan::SetObjectName(device, *fault_process_pipeline, "Fault Buffer Parser Pipeline");

    device.destroyShaderModule(module);
}

void FaultManager::DrainCompletedFaults() {
    if (!mali_safe_fault_drain || draining_faults) return;
    draining_faults = true;
    // Only the producer invokes this at a guest command boundary, never
    // from Scheduler::PopPendingOperations or while submitting the queue.
    // No new GPU wait: consume a strictly ordered prefix of completed areas.
    while (const u64 tick = fault_areas[next_completed_area]) {
        if (!scheduler.GetWorkSemaphore()->IsFree(tick)) break;
        ResolveFaultArea(next_completed_area);
        next_completed_area = (next_completed_area + 1) % MaxPendingFaults;
    }
    draining_faults = false;
}

void FaultManager::ResolveFaultArea(u32 area) {
    const u64 offset = area * PageFaultAreaSize;
    download_buffer.Invalidate(offset, PageFaultAreaSize);
    const auto* mapped = download_buffer.mapped_data.data() + offset;
    const auto* fault_buf = std::bit_cast<const u64*>(mapped);
    // The shader counter is uint32_t, stored in the low half of slot zero.
    const u32 reported = static_cast<u32>(fault_buf[0]);
    const u32 fault_count = FaultResultCount(reported, MaxPageFaults);
    if (reported >= MaxPageFaults)
        std::fprintf(stderr, "GOW3_GPU_FAULT_OVERFLOW reported=%u stored=%u area=%u\n",
                     reported, fault_count, area);
    fault_ranges.Clear();
    for (u32 i = 1; i <= fault_count; ++i) {
        fault_ranges.Add(fault_buf[i], sparse_pagesize);
        LOG_INFO(Render_Vulkan, "Accessed non-GPU cached memory at {:#x}", fault_buf[i]);
    }
    fault_ranges.ForEach([&](VAddr start, VAddr end) {
        ASSERT_MSG((end - start) <= std::numeric_limits<u32>::max(),
                   "Buffer size is too large");
        (void)buffer_cache.ObtainBuffer(start, end - start, false);
    });
    fault_areas[area] = 0;
}

void FaultManager::ProcessFaultBuffer() {
    DrainCompletedFaults();
    if (u64 wait_tick = fault_areas[current_area]) {
        scheduler.Wait(wait_tick);
        if (mali_safe_fault_drain) {
            DrainCompletedFaults();
        } else {
            scheduler.PopPendingOperations();
        }
        ASSERT_MSG(!fault_areas[current_area], "GPU fault result area still in use");
    }

    const u32 offset = current_area * PageFaultAreaSize;
    u8* mapped = download_buffer.mapped_data.data() + offset;
    std::memset(mapped, 0, PageFaultAreaSize);
    download_buffer.Flush(offset, PageFaultAreaSize);

    const vk::BufferMemoryBarrier2 pre_barrier = {
        .srcStageMask = vk::PipelineStageFlagBits2::eAllCommands,
        .srcAccessMask = vk::AccessFlagBits2::eShaderWrite |
                         vk::AccessFlagBits2::eTransferWrite,
        .dstStageMask = vk::PipelineStageFlagBits2::eComputeShader,
        .dstAccessMask = vk::AccessFlagBits2::eShaderRead |
                         vk::AccessFlagBits2::eShaderWrite,
        .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
        .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
        .buffer = fault_buffer.Handle(),
        .offset = 0,
        .size = fault_buffer_size,
    };
    const vk::BufferMemoryBarrier2 post_barrier = {
        .srcStageMask = vk::PipelineStageFlagBits2::eComputeShader,
        .srcAccessMask = vk::AccessFlagBits2::eShaderWrite,
        .dstStageMask = vk::PipelineStageFlagBits2::eAllCommands,
        .dstAccessMask = vk::AccessFlagBits2::eShaderRead |
                         vk::AccessFlagBits2::eShaderWrite,
        .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
        .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
        .buffer = fault_buffer.Handle(),
        .offset = 0,
        .size = fault_buffer_size,
    };
    const vk::DescriptorBufferInfo fault_buffer_info = {
        .buffer = fault_buffer.Handle(),
        .offset = 0,
        .range = fault_buffer_size,
    };
    const vk::DescriptorBufferInfo download_info = {
        .buffer = download_buffer.Handle(),
        .offset = offset,
        .range = PageFaultAreaSize,
    };
    const std::array<vk::WriteDescriptorSet, 2> writes = {{
        {
            .dstSet = VK_NULL_HANDLE,
            .dstBinding = 0,
            .dstArrayElement = 0,
            .descriptorCount = 1,
            .descriptorType = vk::DescriptorType::eStorageBuffer,
            .pBufferInfo = &fault_buffer_info,
        },
        {
            .dstSet = VK_NULL_HANDLE,
            .dstBinding = 1,
            .dstArrayElement = 0,
            .descriptorCount = 1,
            .descriptorType = vk::DescriptorType::eStorageBuffer,
            .pBufferInfo = &download_info,
        },
    }};
    scheduler.EndRendering();
    const auto cmdbuf = scheduler.CommandBuffer();
    cmdbuf.pipelineBarrier2(vk::DependencyInfo{
        .dependencyFlags = vk::DependencyFlagBits::eByRegion,
        .bufferMemoryBarrierCount = 1,
        .pBufferMemoryBarriers = &pre_barrier,
    });
    cmdbuf.bindPipeline(vk::PipelineBindPoint::eCompute, *fault_process_pipeline);
    cmdbuf.pushDescriptorSetKHR(vk::PipelineBindPoint::eCompute, *fault_process_pipeline_layout, 0,
                                writes);
    // 1 bit per page, 32 pages per workgroup
    const u32 num_threads = sparse_num_pages / 32;
    const u32 num_workgroups = Common::DivCeil(num_threads, 64u);
    cmdbuf.dispatch(num_workgroups, 1, 1);

    cmdbuf.pipelineBarrier2(vk::DependencyInfo{
        .dependencyFlags = vk::DependencyFlagBits::eByRegion,
        .bufferMemoryBarrierCount = 1,
        .pBufferMemoryBarriers = &post_barrier,
    });

    // On Mali, do not invoke ObtainBuffer inside a retirement callback:
    // it can allocate an arena, resolve readbacks, or submit recursively
    // while the global queue and submission-order locks are held.
    if (!mali_safe_fault_drain) {
        scheduler.DeferOperation([this, area = current_area] { ResolveFaultArea(area); });
    }

    fault_areas[current_area++] = scheduler.CurrentTick();
    current_area %= MaxPendingFaults;
}

} // namespace VideoCore
