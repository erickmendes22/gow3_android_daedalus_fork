// SPDX-FileCopyrightText: Copyright 2024 shadPS4 Emulator Project
// SPDX-License-Identifier: GPL-2.0-or-later

#include "shader_recompiler/info.h"
#include "video_core/renderer_vulkan/vk_rasterizer.h"
#include "video_core/renderer_vulkan/vk_runtime.h"
#include "video_core/renderer_vulkan/vk_shader_hle.h"
#include "video_core/renderer_vulkan/vk_shader_util.h"
#include "video_core/renderer_vulkan/vk_resource_pool.h"
#include "video_core/renderer_vulkan/vk_instance.h"
#include "video_core/renderer_vulkan/vk_scheduler.h"
#include "video_core/host_shaders/buffer_multi_copy_comp.h"
#include "gow3_toggles.h"
#include "video_core/renderer_vulkan/vk_gpu_profiler.h"

extern std::unique_ptr<AmdGpu::Liverpool> liverpool;

namespace Vulkan {

static constexpr u64 COPY_SHADER_HASH = 0xfefebf9f;

// gow3: the copy shader runs ~57 times per frame with ~1024 small ranges each. As one
// vkCmdCopyBuffer with that many regions it cost ~37 ns of GPU time per range (~2.1 ms per
// frame) plus the recording; buffer_multi_copy.comp copies all ranges in one dispatch.
static bool MultiCopy(Rasterizer& rasterizer, const VideoCore::Buffer* src,
                      const VideoCore::Buffer* dst, std::span<const vk::BufferCopy> copies) {
    if (copies.size() < 8 || Gow3Toggle::Disabled(Gow3Toggle::MultiCopyShader)) {
        return false;
    }
    u64 src_min = ~0ull, src_max = 0, dst_min = ~0ull, dst_max = 0;
    for (const auto& copy : copies) {
        if ((copy.srcOffset | copy.dstOffset | copy.size) & 3) {
            return false; // dword copies only
        }
        src_min = std::min(src_min, copy.srcOffset);
        src_max = std::max(src_max, copy.srcOffset + copy.size);
        dst_min = std::min(dst_min, copy.dstOffset);
        dst_max = std::max(dst_max, copy.dstOffset + copy.size);
    }
    // A single parallel dispatch is not a legal replacement for ordered
    // copies with overlapping source/destination bytes in one VkBuffer.
    // Keep the original transfer path for such aliasing cases.
    if (src->Handle() == dst->Handle() && src_min < dst_max && dst_min < src_max) {
        return false;
    }
    auto& runtime = rasterizer.GetRuntime();
    auto& scheduler = runtime.GetScheduler();
    const auto& instance = runtime.GetInstance();
    // The original compute fast path was silently disabled on all PanVK
    // drivers lacking VK_KHR_push_descriptor. 57 batches/frame x ~1024
    // individual vkCmdCopyBuffer regions then ran on Mali instead. Bind
    // three ordinary storage-buffer descriptors where push is unavailable.
    // Pool recycling is GPU-tick gated by DescriptorHeap, so in-flight
    // submissions can never read an overwritten descriptor.
    const bool push_descriptors = instance.MaxPushDescriptors() >= 3;
    const char* multi_copy_opt_out = std::getenv("GOW3_MALI_MULTI_COPY_PANVK");
    if (!push_descriptors) {
        if (!std::getenv("GOW3_MALI_CPU_PRESENT") ||
            (multi_copy_opt_out && multi_copy_opt_out[0] == '0')) return false;
        // The transfer baseline measured ~37 ns/region on a previous setup.
        // Eight regions save at most 0.30 us of GPU transfer work, far less
        // than a descriptor-set update plus a compute dispatch. Never submit
        // such tiny compute batches on PanVK. The threshold is intentionally
        // conservative pending a real G720 dispatch-time measurement.
        const char* min_opt = std::getenv("GOW3_MALI_MULTI_COPY_MIN_REGIONS");
        const u32 minimum_regions = min_opt ?
            std::clamp<u32>(static_cast<u32>(std::strtoul(min_opt, nullptr, 10)),
                            8u, 1024u) : 256u;
        if (copies.size() < minimum_regions) return false;

        // A compute dispatch launches one workgroup per region, with no
        // ordering between groups. Different-source copies that write the
        // same destination dword must retain ordered vkCmdCopyBuffer.
        // Each 64KiB HLE batch has at most 16384 destination dwords:
        // mark 256 64-bit occupancy words, O(regions + distinct 256B spans).
        constexpr u64 max_batch_bytes = 64_KB;
        if (dst_max - dst_min > max_batch_bytes) return false;
        std::array<u64, max_batch_bytes / 256> writes{};
        for (const auto& region : copies) {
            if (region.dstOffset < dst_min || (region.size & 3)) return false;
            const u64 first = (region.dstOffset - dst_min) / 4;
            const u64 last = first + region.size / 4;
            if (last > max_batch_bytes / 4) return false;
            for (u64 bit = first; bit < last;) {
                const u64 word = bit / 64;
                const u64 end = std::min<u64>(last, (word + 1) * 64);
                const u64 begin_bit = bit % 64;
                const u64 end_bit = end - word * 64;
                const u64 mask = (~0ull << begin_bit) &
                    (end_bit == 64 ? ~0ull : ((1ull << end_bit) - 1));
                if (writes[word] & mask) return false;
                writes[word] |= mask;
                bit = end;
            }
        }
    }
    const u64 align = instance.StorageMinAlignment();
    src_min = Common::AlignDown(src_min, align);
    dst_min = Common::AlignDown(dst_min, align);

    struct Pipeline {
        vk::UniqueDescriptorSetLayout set_layout;
        vk::UniquePipelineLayout layout;
        vk::UniquePipeline pipeline;
        std::unique_ptr<DescriptorHeap> descriptors;
        bool push = false;
    };
    static const std::array<vk::DescriptorPoolSize, 1> copy_pool_sizes{{
        {vk::DescriptorType::eStorageBuffer, 3 * 1024},
    }};
    // Keep this process-lifetime pipeline alive just like the loaded Bionic
    // Vulkan device: a C++ static destructor would otherwise attempt to
    // dereference the scheduler semaphore after the renderer is shut down.
    static Pipeline& pipe = *[&]() -> Pipeline* {
        const auto device = instance.GetDevice();
        auto* allocated = new Pipeline;
        Pipeline& p = *allocated;
        std::array<vk::DescriptorSetLayoutBinding, 3> bindings{};
        for (u32 i = 0; i < 3; ++i) {
            bindings[i] = {.binding = i,
                           .descriptorType = vk::DescriptorType::eStorageBuffer,
                           .descriptorCount = 1,
                           .stageFlags = vk::ShaderStageFlagBits::eCompute};
        }
        p.push = push_descriptors;
        p.set_layout = Check(device.createDescriptorSetLayoutUnique({
            .flags = p.push ? vk::DescriptorSetLayoutCreateFlagBits::ePushDescriptorKHR
                            : vk::DescriptorSetLayoutCreateFlags{},
            .bindingCount = static_cast<u32>(bindings.size()),
            .pBindings = bindings.data(),
        }));
        if (!p.push) {
            p.descriptors = std::make_unique<DescriptorHeap>(
                instance, scheduler.GetWorkSemaphore(), copy_pool_sizes, 1024);
            std::printf("GOW3_MALI_MULTI_COPY_HLE bind=descriptor_set (PanVK no push)\\n");
        }
        const vk::PushConstantRange range{.stageFlags = vk::ShaderStageFlagBits::eCompute,
                                          .offset = 0,
                                          .size = sizeof(u32)};
        p.layout = Check(device.createPipelineLayoutUnique({
            .setLayoutCount = 1,
            .pSetLayouts = &*p.set_layout,
            .pushConstantRangeCount = 1,
            .pPushConstantRanges = &range,
        }));
        const auto module = CompileSPV(BUFFER_MULTI_COPY_COMP, device);
        p.pipeline = Check(device.createComputePipelineUnique(
            {}, vk::ComputePipelineCreateInfo{
                    .stage = {.stage = vk::ShaderStageFlagBits::eCompute,
                              .module = module,
                              .pName = "main"},
                    .layout = *p.layout,
                }));
        device.destroyShaderModule(module);
        return allocated;
    }();

    // The region table goes into the stream buffer (host writes, visible at submission).
    thread_local std::vector<u32> regions;
    regions.resize(copies.size() * 4);
    for (size_t i = 0; i < copies.size(); ++i) {
        regions[i * 4 + 0] = static_cast<u32>((copies[i].srcOffset - src_min) / 4);
        regions[i * 4 + 1] = static_cast<u32>((copies[i].dstOffset - dst_min) / 4);
        regions[i * 4 + 2] = static_cast<u32>(copies[i].size / 4);
        regions[i * 4 + 3] = 0;
    }
    auto& stream = rasterizer.GetBufferCache().GetStreamBuffer();
    const u64 table_size = regions.size() * sizeof(u32);
    const u64 table_offset = stream.Copy(regions.data(), table_size, align);

    if (auto* profiler = GpuProfiler::Get()) {
        profiler->Mark(0xC0B1ull, [] { return std::string{"copy shader HLE: barrier + dispatch"}; });
    }
    scheduler.EndRendering();
    const u64 src_size = src_max - src_min, dst_size = dst_max - dst_min;
    if (runtime.IsBufferAccessed(src, src_min, src_size) ||
        runtime.IsBufferAccessed(dst, dst_min, dst_size, true)) {
        runtime.FlushBarriers();
    }
    const u32 count = static_cast<u32>(copies.size());
    const std::array<vk::DescriptorBufferInfo, 3> infos{{
        {src->Handle(), src_min, src_size},
        {dst->Handle(), dst_min, dst_size},
        {stream.Handle(), table_offset, table_size},
    }};
    vk::DescriptorSet descriptor_set{};
    if (!pipe.push) {
        descriptor_set = pipe.descriptors->Commit(*pipe.set_layout);
        std::array<vk::WriteDescriptorSet, 3> writes{};
        for (u32 i = 0; i < 3; ++i) {
            writes[i] = {.dstSet = descriptor_set,
                         .dstBinding = i,
                         .descriptorCount = 1,
                         .descriptorType = vk::DescriptorType::eStorageBuffer,
                         .pBufferInfo = &infos[i]};
        }
        instance.GetDevice().updateDescriptorSets(writes, {});
    }
    scheduler.Record([infos, descriptor_set, push = pipe.push, layout = *pipe.layout,
                      pipeline = *pipe.pipeline, count](vk::CommandBuffer cmdbuf) {
        cmdbuf.bindPipeline(vk::PipelineBindPoint::eCompute, pipeline);
        if (push) {
            std::array<vk::WriteDescriptorSet, 3> writes{};
            for (u32 i = 0; i < 3; ++i) {
                writes[i] = {.dstBinding = i,
                             .descriptorCount = 1,
                             .descriptorType = vk::DescriptorType::eStorageBuffer,
                             .pBufferInfo = &infos[i]};
            }
            cmdbuf.pushDescriptorSetKHR(vk::PipelineBindPoint::eCompute, layout, 0, writes);
        } else {
            cmdbuf.bindDescriptorSets(vk::PipelineBindPoint::eCompute, layout, 0,
                                     std::array{descriptor_set}, {});
        }
        cmdbuf.pushConstants(layout, vk::ShaderStageFlagBits::eCompute, 0, sizeof(count), &count);
        cmdbuf.dispatch(count, 1, 1);
    });
    runtime.AccessBuffer(src, src_min, src_size, vk::PipelineStageFlagBits2::eComputeShader,
                         vk::AccessFlagBits2::eShaderRead);
    runtime.AccessBuffer(dst, dst_min, dst_size, vk::PipelineStageFlagBits2::eComputeShader,
                         vk::AccessFlagBits2::eShaderWrite);
    return true;
}

static bool ExecuteCopyShaderHLE(const Shader::Info& info, const AmdGpu::ComputeProgram& cs_program,
                                 Rasterizer& rasterizer) {
    auto& runtime = rasterizer.GetRuntime();
    auto& buffer_cache = rasterizer.GetBufferCache();

    // Copy shader defines three formatted buffers as inputs: control, source, and destination.
    const auto ctl_buf_sharp = info.buffers[0].GetSharp(info);
    const auto src_buf_sharp = info.buffers[1].GetSharp(info);
    const auto dst_buf_sharp = info.buffers[2].GetSharp(info);
    const auto buf_stride = src_buf_sharp.GetStride();
    ASSERT(buf_stride == dst_buf_sharp.GetStride());

    struct CopyShaderControl {
        u32 dst_idx;
        u32 src_idx;
        u32 end;
    };
    static_assert(sizeof(CopyShaderControl) == 12);
    ASSERT(ctl_buf_sharp.GetStride() == sizeof(CopyShaderControl));
    const auto ctl_buf = reinterpret_cast<const CopyShaderControl*>(ctl_buf_sharp.base_address);

    static std::vector<vk::BufferCopy> copies;
    copies.clear();
    copies.reserve(cs_program.dim_x);

    for (u32 i = 0; i < cs_program.dim_x; i++) {
        const auto& [dst_idx, src_idx, end] = ctl_buf[i];
        const u32 local_dst_offset = dst_idx * buf_stride;
        const u32 local_src_offset = src_idx * buf_stride;
        const u32 local_size = (end + 1) * buf_stride;
        copies.emplace_back(local_src_offset, local_dst_offset, local_size);
    }

    // gow3: 64 KiB instead of 64 MiB. The copies are a few KiB spread over up to 57 MiB, and
    // each batch synchronizes (uploads, marks GPU-modified) its whole range: GPU time of the copy
    // shader 1.5 -> 0.6 ms/frame, GPU busy 85% -> 77%, frame rate no lower.
    // GOW3_COPY_MERGE_KB overrides it.
    static const vk::DeviceSize MaxDistanceForMerge = [] {
        const char* env = std::getenv("GOW3_COPY_MERGE_KB");
        return env ? vk::DeviceSize(std::strtoull(env, nullptr, 10)) * 1024 : vk::DeviceSize(64_KB);
    }();
    static thread_local std::vector<VideoCore::CopyRange> source_ranges, destination_ranges;
    source_ranges.reserve(copies.size());
    destination_ranges.reserve(copies.size());
    u32 batch_start = 0;
    u32 batch_end = 0;

    while (batch_end < copies.size()) {
        // Place first copy into the current batch
        const auto& copy = copies[batch_start];
        auto src_offset_min = copy.srcOffset;
        auto src_offset_max = copy.srcOffset + copy.size;
        auto dst_offset_min = copy.dstOffset;
        auto dst_offset_max = copy.dstOffset + copy.size;

        for (++batch_end; batch_end < copies.size(); batch_end++) {
            // Compute new src and dst bounds if we were to batch this copy
            const auto& [src_offset, dst_offset, size] = copies[batch_end];
            auto new_src_offset_min = std::min(src_offset_min, src_offset);
            auto new_src_offset_max = std::max(src_offset_max, src_offset + size);
            if (new_src_offset_max - new_src_offset_min > MaxDistanceForMerge) {
                break;
            }

            auto new_dst_offset_min = std::min(dst_offset_min, dst_offset);
            auto new_dst_offset_max = std::max(dst_offset_max, dst_offset + size);
            if (new_dst_offset_max - new_dst_offset_min > MaxDistanceForMerge) {
                break;
            }

            // We can batch this copy
            src_offset_min = new_src_offset_min;
            src_offset_max = new_src_offset_max;
            dst_offset_min = new_dst_offset_min;
            dst_offset_max = new_dst_offset_max;
        }

        // Preserve the 64 KiB grouping and MultiCopy shader, but upload/mark only the
        // intervals actually copied instead of every byte between the batch bounds.
        source_ranges.clear();
        destination_ranges.clear();
        for (const auto& region : std::span{copies}.subspan(batch_start, batch_end - batch_start)) {
            source_ranges.emplace_back(u32(region.srcOffset - src_offset_min), u32(region.size));
            destination_ranges.emplace_back(u32(region.dstOffset - dst_offset_min), u32(region.size));
        }
        const auto [src_buf, src_buf_offset] = buffer_cache.ObtainBufferRanges(
            src_buf_sharp.base_address + src_offset_min, u32(src_offset_max - src_offset_min),
            source_ranges, false);
        const auto [dst_buf, dst_buf_offset] = buffer_cache.ObtainBufferRanges(
            dst_buf_sharp.base_address + dst_offset_min, u32(dst_offset_max - dst_offset_min),
            destination_ranges, true);

        // Apply found buffer base.
        const auto vk_copies = std::span{copies}.subspan(batch_start, batch_end - batch_start);
        for (auto& copy : vk_copies) {
            copy.srcOffset = copy.srcOffset - src_offset_min + src_buf_offset;
            copy.dstOffset = copy.dstOffset - dst_offset_min + dst_buf_offset;
        }

        // Execute buffer copies.
        LOG_TRACE(Render_Vulkan, "HLE buffer copy: src_size = {}, dst_size = {}",
                  src_offset_max - src_offset_min, dst_offset_max - dst_offset_min);
        if (!MultiCopy(rasterizer, src_buf, dst_buf, vk_copies)) {
            runtime.CopyBuffer(src_buf, dst_buf, vk_copies);
        }
        batch_start = batch_end;
    }

    return true;
}

bool ExecuteShaderHLE(const Shader::Info& info, const AmdGpu::Regs& regs,
                      const AmdGpu::ComputeProgram& cs_program, Rasterizer& rasterizer) {
    switch (info.pgm_hash) {
    case COPY_SHADER_HASH:
        return ExecuteCopyShaderHLE(info, cs_program, rasterizer);
    default:
        return false;
    }
}

} // namespace Vulkan
