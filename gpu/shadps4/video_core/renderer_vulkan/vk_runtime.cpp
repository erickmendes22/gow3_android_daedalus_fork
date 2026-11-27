// SPDX-FileCopyrightText: Copyright 2025 shadPS4 Emulator Project
// SPDX-License-Identifier: GPL-2.0-or-later

#include <boost/container/small_vector.hpp>
#include <bit>
#include <cstdlib>
#include "gow3_toggles.h"
#include "video_core/buffer_cache/buffer.h"
#include "video_core/renderer_vulkan/liverpool_to_vk.h"
#include "video_core/renderer_vulkan/vk_instance.h"
#include "video_core/renderer_vulkan/vk_runtime.h"
#include "video_core/renderer_vulkan/vk_gpu_profiler.h"
#include "video_core/renderer_vulkan/vk_mali_perf_stats.h"
#include "video_core/renderer_vulkan/vk_scene_resolution.h"
#include "video_core/renderer_vulkan/vk_scheduler.h"
#include "video_core/renderer_vulkan/vk_resource_pool.h"
#include "video_core/renderer_vulkan/vk_shader_util.h"
#include "video_core/host_shaders/bcn_to_etc2_comp.h"
#include "video_core/host_shaders/snorm2101010_comp.h"
#include <array>
#include <algorithm>
#include <limits>
#include "video_core/texture_cache/blit_helper.h"
#include "video_core/texture_cache/image.h"

#include <vulkan/vulkan_format_traits.hpp>

namespace Vulkan {

// Pipeline and descriptor lifetime are owned by Runtime. All scratch buffers are
// allocated from the existing GPU-tick-aware staging pool, not CPU-mapped RGBA.
struct BcnTranscodeState {
    const Instance& instance;
    Scheduler& scheduler;
    // Same fast path as the universal TLOU GPU BC decoder where supported.
    // When VK_KHR_push_descriptor is missing, keep the tick-safe descriptor heap.
    bool use_push_descriptors{};
    const std::array<vk::DescriptorPoolSize, 1> sizes{{
        {vk::DescriptorType::eStorageBuffer, 256},
    }};
    DescriptorHeap descriptor_heap;
    vk::UniqueDescriptorSetLayout descriptor_layout;
    vk::UniquePipelineLayout pipeline_layout;
    vk::UniquePipeline pipeline;

    struct Params {
        u32 blocks_x;
        u32 blocks_y;
        u32 input_row_blocks;
        u32 input_base_words;
        u32 bc_words;
    };
    static_assert(sizeof(Params) == 20);

    BcnTranscodeState(const Instance& inst, Scheduler& sched)
        : instance{inst}, scheduler{sched},
          use_push_descriptors{inst.MaxPushDescriptors() >= 2},
          descriptor_heap{inst, sched.GetWorkSemaphore(), sizes, 128} {
        const auto device = instance.GetDevice();
        const std::array<vk::DescriptorSetLayoutBinding, 2> bindings{{
            {.binding = 0, .descriptorType = vk::DescriptorType::eStorageBuffer,
             .descriptorCount = 1, .stageFlags = vk::ShaderStageFlagBits::eCompute},
            {.binding = 1, .descriptorType = vk::DescriptorType::eStorageBuffer,
             .descriptorCount = 1, .stageFlags = vk::ShaderStageFlagBits::eCompute},
        }};
        const vk::DescriptorSetLayoutCreateInfo descriptor_ci{
            .flags = use_push_descriptors ? vk::DescriptorSetLayoutCreateFlagBits::ePushDescriptorKHR
                                          : vk::DescriptorSetLayoutCreateFlags{},
            .bindingCount = static_cast<u32>(bindings.size()),
            .pBindings = bindings.data(),
        };
        auto [layout_result, layout] = device.createDescriptorSetLayoutUnique(descriptor_ci);
        ASSERT_MSG(layout_result == vk::Result::eSuccess,
                   "Mali ETC2 descriptor layout failed: {}", vk::to_string(layout_result));
        descriptor_layout = std::move(layout);
        const vk::DescriptorSetLayout raw_layout = *descriptor_layout;
        const vk::PushConstantRange pc_range{
            .stageFlags = vk::ShaderStageFlagBits::eCompute,
            .offset = 0, .size = sizeof(Params),
        };
        const vk::PipelineLayoutCreateInfo pipeline_layout_ci{
            .setLayoutCount = 1,
            .pSetLayouts = &raw_layout,
            .pushConstantRangeCount = 1,
            .pPushConstantRanges = &pc_range,
        };
        auto [pl_result, pl] = device.createPipelineLayoutUnique(pipeline_layout_ci);
        ASSERT_MSG(pl_result == vk::Result::eSuccess,
                   "Mali ETC2 pipeline layout failed: {}", vk::to_string(pl_result));
        pipeline_layout = std::move(pl);
        const auto shader = CompileSPV(std::span<const u32>{BCN_TO_ETC2_COMP}, device);
        const vk::PipelineShaderStageCreateInfo shader_ci{
            .stage = vk::ShaderStageFlagBits::eCompute, .module = shader, .pName = "main",
        };
        const vk::ComputePipelineCreateInfo pipeline_ci{
            .stage = shader_ci, .layout = *pipeline_layout,
        };
        auto [p_result, p] = device.createComputePipelineUnique(VK_NULL_HANDLE, pipeline_ci);
        device.destroyShaderModule(shader);
        ASSERT_MSG(p_result == vk::Result::eSuccess,
                   "Mali BCn-to-ETC2 compute pipeline failed: {}", vk::to_string(p_result));
        pipeline = std::move(p);
        std::printf("GOW3_MALI_BCN_TO_ETC2 compute pipeline ready descriptor_mode=%s\n",
                    use_push_descriptors ? "push" : "pool");
    }

    // TLOU-style multi-mip batching. One GPU-tick-protected scratch reservation
    // and one recorded command encode many independent mip uploads. The guest
    // BC data, mip order and exact ETC2 copy offsets are unchanged. Keep the
    // original per-mip path as a fallback for large or unusual transfers.
    struct BatchPass {
        Params params{};
        vk::DescriptorBufferInfo input{};
        vk::DescriptorBufferInfo output{};
        vk::BufferImageCopy copy{};
        vk::DescriptorSet set{};
        u64 local_offset{};
        u64 output_bytes{};
    };

    bool RecordBatch(VideoCore::Image* dst, const VideoCore::Buffer* src,
                     std::span<const vk::BufferImageCopy> copies, StagingBufferPool& staging,
                     u32 words, const vk::PhysicalDeviceLimits& limits, u64 alignment) {
        // Bound both command-record storage and the staging ring footprint.
        // A single-mip or oversized request uses the previously verified path.
        constexpr u64 MaxBatchBytes = 8ULL * 1024 * 1024;
        if (copies.size() < 2 || copies.size() > 24) return false;
        // Normal PS4 mip chains fit the inline 14-pass array, avoiding an
        // additional heap allocation in the texture-upload CPU hot path.
        boost::container::small_vector<BatchPass, 14> passes;
        u64 total = 0;
        const u64 source_size = src->SizeBytes();
        for (const auto& copy : copies) {
            if (copy.imageExtent.depth != 1 || copy.imageSubresource.layerCount != 1 ||
                !copy.imageExtent.width || !copy.imageExtent.height ||
                copy.imageOffset.x < 0 || copy.imageOffset.y < 0 || copy.imageOffset.z != 0)
                return false;
            const u32 width = (copy.imageExtent.width + 3u) / 4u;
            const u32 height = (copy.imageExtent.height + 3u) / 4u;
            if ((u64(width) + 7u) / 8u > limits.maxComputeWorkGroupCount[0] ||
                (u64(height) + 7u) / 8u > limits.maxComputeWorkGroupCount[1])
                return false;
            const u32 row_texels = copy.bufferRowLength ? copy.bufferRowLength
                                                       : copy.imageExtent.width;
            const u32 rows_texels = copy.bufferImageHeight ? copy.bufferImageHeight
                                                           : copy.imageExtent.height;
            if (row_texels < copy.imageExtent.width || rows_texels < copy.imageExtent.height)
                return false;
            const u64 row_blocks = (u64(row_texels) + 3u) / 4u;
            const u64 last_bytes = ((u64(height) - 1u) * row_blocks + width) * words * 4u;
            const u64 output_bytes = u64(width) * height * 16u;
            if (output_bytes > limits.maxStorageBufferRange ||
                last_bytes > limits.maxStorageBufferRange ||
                copy.bufferOffset > source_size)
                return false;
            const u64 base = (copy.bufferOffset / alignment) * alignment;
            const u64 relative = copy.bufferOffset - base;
            const u64 in_range = relative + last_bytes;
            if (relative % 4u || relative > std::numeric_limits<u32>::max() ||
                in_range > limits.maxStorageBufferRange || base > source_size ||
                in_range > source_size - base)
                return false;
            // Every copy destination needs 16-byte block alignment and a
            // storage-buffer-aligned start. No two passes overlap in scratch.
            const u64 aligned = (total + alignment - 1u) / alignment * alignment;
            if (aligned > MaxBatchBytes || output_bytes > MaxBatchBytes - aligned)
                return false;
            BatchPass pass{};
            pass.params = Params{width, height, static_cast<u32>(row_blocks),
                                 static_cast<u32>(relative / 4u), words};
            pass.input.offset = base;
            pass.input.range = in_range;
            pass.local_offset = aligned;
            pass.output_bytes = output_bytes;
            pass.copy = copy;
            pass.copy.bufferRowLength = 0;
            pass.copy.bufferImageHeight = 0;
            passes.push_back(pass);
            total = aligned + output_bytes;
        }
        if (!total) return false;

        // Reserve only after every region validates; never partially record a
        // transcode and then fall back to re-uploading half the mip chain.
        const auto scratch = staging.Request(total, VideoCore::MemoryType::DeviceLocal,
                                             alignment);
        const auto buffer = scratch.buffer->Handle();
        const auto device = instance.GetDevice();
        for (auto& pass : passes) {
            pass.input.buffer = src->Handle();
            pass.output.buffer = buffer;
            pass.output.offset = scratch.offset + pass.local_offset;
            pass.output.range = pass.output_bytes;
            pass.copy.bufferOffset = pass.output.offset;
            if (!use_push_descriptors) {
                pass.set = descriptor_heap.Commit(*descriptor_layout);
                const std::array<vk::WriteDescriptorSet, 2> writes{{
                    {.dstSet = pass.set, .dstBinding = 0, .descriptorCount = 1,
                     .descriptorType = vk::DescriptorType::eStorageBuffer,
                     .pBufferInfo = &pass.input},
                    {.dstSet = pass.set, .dstBinding = 1, .descriptorCount = 1,
                     .descriptorType = vk::DescriptorType::eStorageBuffer,
                     .pBufferInfo = &pass.output},
                }};
                device.updateDescriptorSets(writes, {});
            }
        }
        const vk::BufferMemoryBarrier2 all_compute_to_copy{
            .srcStageMask = vk::PipelineStageFlagBits2::eComputeShader,
            .srcAccessMask = vk::AccessFlagBits2::eShaderWrite,
            .dstStageMask = vk::PipelineStageFlagBits2::eCopy,
            .dstAccessMask = vk::AccessFlagBits2::eTransferRead,
            .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
            .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
            .buffer = buffer, .offset = scratch.offset, .size = total,
        };
        scheduler.Record([pipeline = *pipeline, layout = *pipeline_layout,
                          image = dst->GetImage(), buffer,
                          push = use_push_descriptors, all_compute_to_copy,
                          passes = scheduler.RecordData(std::span<const BatchPass>{passes.data(), passes.size()})](
                             vk::CommandBuffer cb) {
            cb.bindPipeline(vk::PipelineBindPoint::eCompute, pipeline);
            for (const auto& pass : passes) {
                if (push) {
                    const std::array<vk::WriteDescriptorSet, 2> writes{{
                        {.dstBinding = 0, .descriptorCount = 1,
                         .descriptorType = vk::DescriptorType::eStorageBuffer,
                         .pBufferInfo = &pass.input},
                        {.dstBinding = 1, .descriptorCount = 1,
                         .descriptorType = vk::DescriptorType::eStorageBuffer,
                         .pBufferInfo = &pass.output},
                    }};
                    cb.pushDescriptorSetKHR(vk::PipelineBindPoint::eCompute, layout, 0, writes);
                } else {
                    cb.bindDescriptorSets(vk::PipelineBindPoint::eCompute, layout, 0, pass.set, {});
                }
                cb.pushConstants(layout, vk::ShaderStageFlagBits::eCompute, 0,
                                 sizeof(Params), &pass.params);
                cb.dispatch((pass.params.blocks_x + 7u) / 8u,
                            (pass.params.blocks_y + 7u) / 8u, 1);
            }
            // One barrier covers all disjoint writes. Only then copy the
            // completed compressed data into each original mip subresource.
            const vk::DependencyInfo barrier{
                .bufferMemoryBarrierCount = 1, .pBufferMemoryBarriers = &all_compute_to_copy,
            };
            cb.pipelineBarrier2(barrier);
            for (const auto& pass : passes) {
                cb.copyBufferToImage(buffer, image, vk::ImageLayout::eTransferDstOptimal,
                                     pass.copy);
            }
        });
        return true;
    }

    bool Record(VideoCore::Image* dst, const VideoCore::Buffer* src,
                std::span<const vk::BufferImageCopy> copies, StagingBufferPool& staging) {
        const vk::Format guest = dst->info.pixel_format;
        const bool bc1 = guest == vk::Format::eBc1RgbaUnormBlock ||
                         guest == vk::Format::eBc1RgbaSrgbBlock;
        const bool bc3 = guest == vk::Format::eBc3UnormBlock ||
                         guest == vk::Format::eBc3SrgbBlock;
        if (!bc1 && !bc3) return false;
        const u32 words = bc1 ? 2u : 4u;
        const auto& limits = instance.GetPhysicalDevice().getProperties().limits;
        const u64 alignment = std::max<u64>(16, limits.minStorageBufferOffsetAlignment);
        if (RecordBatch(dst, src, copies, staging, words, limits, alignment))
            return true;
        const auto device = instance.GetDevice();
        for (const auto& copy : copies) {
            if (copy.imageExtent.depth != 1 || !copy.imageExtent.width ||
                !copy.imageExtent.height || !copy.imageSubresource.layerCount ||
                copy.imageOffset.z != 0 || copy.imageOffset.x < 0 || copy.imageOffset.y < 0)
                return false;
            const u32 blocks_x = (copy.imageExtent.width + 3u) / 4u;
            const u32 blocks_y = (copy.imageExtent.height + 3u) / 4u;
            const u32 row_texels = copy.bufferRowLength ? copy.bufferRowLength : copy.imageExtent.width;
            const u32 rows_texels = copy.bufferImageHeight ? copy.bufferImageHeight : copy.imageExtent.height;
            if (row_texels < copy.imageExtent.width || rows_texels < copy.imageExtent.height)
                return false;
            const u32 src_row_blocks = (row_texels + 3u) / 4u;
            const u32 src_rows_blocks = (rows_texels + 3u) / 4u;
            const u64 layer_stride = u64(src_row_blocks) * src_rows_blocks * words * 4;
            const u64 last_bytes = (u64(blocks_y - 1u) * src_row_blocks + blocks_x) * words * 4;
            const u64 output_bytes = u64(blocks_x) * blocks_y * 16;
            if (output_bytes > limits.maxStorageBufferRange ||
                last_bytes > limits.maxStorageBufferRange)
                return false;
            for (u32 layer = 0; layer < copy.imageSubresource.layerCount; ++layer) {
                const u64 source_start = copy.bufferOffset + u64(layer) * layer_stride;
                const u64 base = (source_start / alignment) * alignment;
                const u64 in_range = source_start - base + last_bytes;
                if (base > src->SizeBytes() || in_range > src->SizeBytes() - base ||
                    in_range > limits.maxStorageBufferRange ||
                    source_start - base > std::numeric_limits<u32>::max())
                    return false;
                // Small transcodes use the existing 16 MiB device-local stream ring,
                // avoiding one VMA buffer allocation per BC texture. Reserve()
                // marks every range with the current GPU completion tick, so
                // queued dispatches cannot be overwritten before retirement.
                // Larger-than-16 MiB requests use the pool's tick-guarded cache.
                const auto scratch = staging.Request(output_bytes, VideoCore::MemoryType::DeviceLocal,
                                                     alignment);
                const vk::DescriptorBufferInfo in{
                    .buffer = src->Handle(), .offset = base, .range = in_range,
                };
                const vk::DescriptorBufferInfo out{
                    .buffer = scratch.buffer->Handle(), .offset = scratch.offset,
                    .range = output_bytes,
                };
                const vk::DescriptorSet set = use_push_descriptors
                    ? vk::DescriptorSet{} : descriptor_heap.Commit(*descriptor_layout);
                const std::array<vk::WriteDescriptorSet, 2> writes{{
                    {.dstSet = set, .dstBinding = 0, .descriptorCount = 1,
                     .descriptorType = vk::DescriptorType::eStorageBuffer, .pBufferInfo = &in},
                    {.dstSet = set, .dstBinding = 1, .descriptorCount = 1,
                     .descriptorType = vk::DescriptorType::eStorageBuffer, .pBufferInfo = &out},
                }};
                if (!use_push_descriptors) device.updateDescriptorSets(writes, {});
                const Params params{
                    blocks_x, blocks_y, src_row_blocks,
                    static_cast<u32>((source_start - base) / 4u), words,
                };
                vk::BufferImageCopy out_copy = copy;
                out_copy.bufferOffset = scratch.offset;
                out_copy.bufferRowLength = 0;
                out_copy.bufferImageHeight = 0;
                out_copy.imageSubresource.baseArrayLayer += layer;
                out_copy.imageSubresource.layerCount = 1;
                const vk::BufferMemoryBarrier2 scratch_barrier{
                    .srcStageMask = vk::PipelineStageFlagBits2::eComputeShader,
                    .srcAccessMask = vk::AccessFlagBits2::eShaderWrite,
                    .dstStageMask = vk::PipelineStageFlagBits2::eCopy,
                    .dstAccessMask = vk::AccessFlagBits2::eTransferRead,
                    .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
                    .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
                    .buffer = scratch.buffer->Handle(),
                    .offset = scratch.offset,
                    .size = output_bytes,
                };
                scheduler.Record([pipeline = *pipeline, layout = *pipeline_layout,
                                  image = dst->GetImage(), scratch_buffer = scratch.buffer->Handle(),
                                  set, in, out, use_push_descriptors = use_push_descriptors,
                                  params, out_copy, scratch_barrier](vk::CommandBuffer cb) {
                    cb.bindPipeline(vk::PipelineBindPoint::eCompute, pipeline);
                    if (use_push_descriptors) {
                        // Push descriptors are recorded inline with the dispatch:
                        // no descriptor-set allocation or vkUpdateDescriptorSets on
                        // the texture-upload CPU thread. Capture buffer infos by
                        // value so asynchronous command recording is safe.
                        const std::array<vk::WriteDescriptorSet, 2> push_writes{{
                            {.dstBinding = 0, .descriptorCount = 1,
                             .descriptorType = vk::DescriptorType::eStorageBuffer,
                             .pBufferInfo = &in},
                            {.dstBinding = 1, .descriptorCount = 1,
                             .descriptorType = vk::DescriptorType::eStorageBuffer,
                             .pBufferInfo = &out},
                        }};
                        cb.pushDescriptorSetKHR(vk::PipelineBindPoint::eCompute, layout, 0,
                                                push_writes);
                    } else {
                        cb.bindDescriptorSets(vk::PipelineBindPoint::eCompute, layout, 0, set, {});
                    }
                    cb.pushConstants(layout, vk::ShaderStageFlagBits::eCompute,
                                     0, sizeof(Params), &params);
                    cb.dispatch((params.blocks_x + 7u) / 8u, (params.blocks_y + 7u) / 8u, 1);
                    const vk::DependencyInfo barrier{
                        .bufferMemoryBarrierCount = 1, .pBufferMemoryBarriers = &scratch_barrier,
                    };
                    cb.pipelineBarrier2(barrier);
                    cb.copyBufferToImage(scratch_buffer, image,
                                         vk::ImageLayout::eTransferDstOptimal, out_copy);
                });
                // StreamBuffer::Reserve and RequestLarge both retain storage
                // until scheduler.IsFree(tick); there is no deferred hold to release.
            }
        }
        return true;
    }
};


struct SnormTranscodeState {
    const Instance& instance;
    Scheduler& scheduler;
    bool use_push_descriptors{};
    const std::array<vk::DescriptorPoolSize, 1> sizes{{
        {vk::DescriptorType::eStorageBuffer, 256},
    }};
    DescriptorHeap descriptor_heap;
    vk::UniqueDescriptorSetLayout descriptor_layout;
    vk::UniquePipelineLayout pipeline_layout;
    vk::UniquePipeline pipeline;

    struct Params {
        u32 width, height, input_row_texels, output_row_texels;
        u32 input_start_words, output_start_words, direction;
    };
    static_assert(sizeof(Params) == 28);

    SnormTranscodeState(const Instance& inst, Scheduler& sched)
        : instance{inst}, scheduler{sched},
          use_push_descriptors{inst.MaxPushDescriptors() >= 2},
          descriptor_heap{inst, sched.GetWorkSemaphore(), sizes, 128} {
        const auto device = instance.GetDevice();
        const std::array<vk::DescriptorSetLayoutBinding, 2> bindings{{
            {.binding = 0, .descriptorType = vk::DescriptorType::eStorageBuffer,
             .descriptorCount = 1, .stageFlags = vk::ShaderStageFlagBits::eCompute},
            {.binding = 1, .descriptorType = vk::DescriptorType::eStorageBuffer,
             .descriptorCount = 1, .stageFlags = vk::ShaderStageFlagBits::eCompute},
        }};
        const vk::DescriptorSetLayoutCreateInfo descriptor_ci{
            .flags = use_push_descriptors
                         ? vk::DescriptorSetLayoutCreateFlagBits::ePushDescriptorKHR
                         : vk::DescriptorSetLayoutCreateFlags{},
            .bindingCount = static_cast<u32>(bindings.size()),
            .pBindings = bindings.data(),
        };
        auto [lr, layout] = device.createDescriptorSetLayoutUnique(descriptor_ci);
        ASSERT_MSG(lr == vk::Result::eSuccess, "SNORM10 descriptor layout failed: {}",
                   vk::to_string(lr));
        descriptor_layout = std::move(layout);
        const vk::DescriptorSetLayout raw_layout = *descriptor_layout;
        const vk::PushConstantRange push{
            .stageFlags = vk::ShaderStageFlagBits::eCompute,
            .offset = 0, .size = sizeof(Params),
        };
        const vk::PipelineLayoutCreateInfo layout_ci{
            .setLayoutCount = 1, .pSetLayouts = &raw_layout,
            .pushConstantRangeCount = 1, .pPushConstantRanges = &push,
        };
        auto [pr, pipeline_layout_handle] = device.createPipelineLayoutUnique(layout_ci);
        ASSERT_MSG(pr == vk::Result::eSuccess, "SNORM10 pipeline layout failed: {}",
                   vk::to_string(pr));
        pipeline_layout = std::move(pipeline_layout_handle);
        const auto shader = CompileSPV(std::span<const u32>{SNORM2101010_COMP}, device);
        const vk::PipelineShaderStageCreateInfo stage{
            .stage = vk::ShaderStageFlagBits::eCompute, .module = shader, .pName = "main",
        };
        const vk::ComputePipelineCreateInfo create{
            .stage = stage, .layout = *pipeline_layout,
        };
        auto [cr, created] = device.createComputePipelineUnique(VK_NULL_HANDLE, create);
        device.destroyShaderModule(shader);
        ASSERT_MSG(cr == vk::Result::eSuccess, "SNORM10 GPU converter failed: {}",
                   vk::to_string(cr));
        pipeline = std::move(created);
    }

    bool Record(VideoCore::Image* image, const VideoCore::Buffer* other,
                std::span<const vk::BufferImageCopy> regions, StagingBufferPool& staging,
                bool upload) {
        const auto& limits = instance.GetPhysicalDevice().getProperties().limits;
        const u64 alignment = std::max<u64>(16, limits.minStorageBufferOffsetAlignment);
        // Validate ALL regions before recording any Vulkan commands. An
        // unsupported transfer must not leave a partially updated mip chain.
        for (const auto& copy : regions) {
            const u64 width = copy.imageExtent.width, height = copy.imageExtent.height;
            const u64 row = copy.bufferRowLength ? copy.bufferRowLength : width;
            const u64 rows = copy.bufferImageHeight ? copy.bufferImageHeight : height;
            const u64 pixels = width * height;
            if (!width || !height || width > UINT32_MAX / height ||
                copy.imageExtent.depth != 1 || copy.imageOffset.z != 0 ||
                copy.imageOffset.x < 0 || copy.imageOffset.y < 0 ||
                !copy.imageSubresource.layerCount || row < width || rows < height ||
                (width + 7u) / 8u > limits.maxComputeWorkGroupCount[0] ||
                (height + 7u) / 8u > limits.maxComputeWorkGroupCount[1] ||
                pixels * 8u > limits.maxStorageBufferRange)
                return false;
            const u64 per_layer = row * rows * 4u;
            const u64 last_pixel = ((height - 1u) * row + width) * 4u;
            const u64 last_layer = u64(copy.imageSubresource.layerCount - 1u) * per_layer;
            if (copy.bufferOffset > other->SizeBytes() ||
                last_layer + last_pixel > other->SizeBytes() - copy.bufferOffset ||
                (copy.bufferOffset % 4u) != 0)
                return false;
        }
        const auto device = instance.GetDevice();
        for (const auto& copy : regions) {
            const u32 width = copy.imageExtent.width, height = copy.imageExtent.height;
            const u32 row = copy.bufferRowLength ? copy.bufferRowLength : width;
            const u32 rows = copy.bufferImageHeight ? copy.bufferImageHeight : height;
            const u64 scratch_bytes = u64(width) * height * 8u;
            for (u32 layer = 0; layer < copy.imageSubresource.layerCount; ++layer) {
                const u64 guest_start = copy.bufferOffset + u64(layer) * row * rows * 4u;
                const u64 guest_base = guest_start / alignment * alignment;
                const u64 guest_span = guest_start - guest_base +
                                       (u64(height - 1u) * row + width) * 4u;
                if (guest_span > limits.maxStorageBufferRange ||
                    guest_start - guest_base > UINT32_MAX) return false;
                const auto scratch = staging.Request(
                    scratch_bytes, VideoCore::MemoryType::DeviceLocal, alignment);
                const vk::DescriptorBufferInfo guest_info{
                    .buffer = other->Handle(), .offset = guest_base, .range = guest_span,
                };
                const vk::DescriptorBufferInfo scratch_info{
                    .buffer = scratch.buffer->Handle(), .offset = scratch.offset,
                    .range = scratch_bytes,
                };
                const vk::DescriptorBufferInfo in = upload ? guest_info : scratch_info;
                const vk::DescriptorBufferInfo out = upload ? scratch_info : guest_info;
                const vk::DescriptorSet set = use_push_descriptors
                    ? vk::DescriptorSet{} : descriptor_heap.Commit(*descriptor_layout);
                const std::array<vk::WriteDescriptorSet, 2> writes{{
                    {.dstSet = set, .dstBinding = 0, .descriptorCount = 1,
                     .descriptorType = vk::DescriptorType::eStorageBuffer, .pBufferInfo = &in},
                    {.dstSet = set, .dstBinding = 1, .descriptorCount = 1,
                     .descriptorType = vk::DescriptorType::eStorageBuffer, .pBufferInfo = &out},
                }};
                if (!use_push_descriptors) device.updateDescriptorSets(writes, {});
                const Params params{
                    .width = width, .height = height,
                    .input_row_texels = upload ? row : width,
                    .output_row_texels = upload ? width : row,
                    .input_start_words = upload ? u32((guest_start - guest_base) / 4u) : 0u,
                    .output_start_words = upload ? 0u : u32((guest_start - guest_base) / 4u),
                    .direction = upload ? 0u : 1u,
                };
                vk::BufferImageCopy image_copy = copy;
                image_copy.bufferOffset = scratch.offset;
                image_copy.bufferRowLength = 0;
                image_copy.bufferImageHeight = 0;
                image_copy.imageSubresource.baseArrayLayer += layer;
                image_copy.imageSubresource.layerCount = 1;
                const vk::BufferMemoryBarrier2 scratch_barrier{
                    .srcStageMask = upload ? vk::PipelineStageFlagBits2::eComputeShader
                                           : vk::PipelineStageFlagBits2::eCopy,
                    .srcAccessMask = upload ? vk::AccessFlagBits2::eShaderWrite
                                            : vk::AccessFlagBits2::eTransferWrite,
                    .dstStageMask = upload ? vk::PipelineStageFlagBits2::eCopy
                                           : vk::PipelineStageFlagBits2::eComputeShader,
                    .dstAccessMask = upload ? vk::AccessFlagBits2::eTransferRead
                                            : vk::AccessFlagBits2::eShaderRead,
                    .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
                    .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
                    .buffer = scratch.buffer->Handle(), .offset = scratch.offset,
                    .size = scratch_bytes,
                };
                scheduler.Record([
                    pipeline = *pipeline, layout = *pipeline_layout,
                    image_handle = image->GetImage(), scratch_buffer = scratch.buffer->Handle(),
                    set, push = use_push_descriptors, in, out, params, image_copy,
                    scratch_barrier, upload
                ](vk::CommandBuffer cb) {
                    const vk::DependencyInfo barrier{
                        .bufferMemoryBarrierCount = 1,
                        .pBufferMemoryBarriers = &scratch_barrier,
                    };
                    if (!upload) {
                        cb.copyImageToBuffer(image_handle,
                                             vk::ImageLayout::eTransferSrcOptimal,
                                             scratch_buffer, image_copy);
                        cb.pipelineBarrier2(barrier);
                    }
                    cb.bindPipeline(vk::PipelineBindPoint::eCompute, pipeline);
                    if (push) {
                        const std::array<vk::WriteDescriptorSet, 2> w{{
                            {.dstBinding = 0, .descriptorCount = 1,
                             .descriptorType = vk::DescriptorType::eStorageBuffer, .pBufferInfo = &in},
                            {.dstBinding = 1, .descriptorCount = 1,
                             .descriptorType = vk::DescriptorType::eStorageBuffer, .pBufferInfo = &out},
                        }};
                        cb.pushDescriptorSetKHR(vk::PipelineBindPoint::eCompute, layout, 0, w);
                    } else {
                        cb.bindDescriptorSets(vk::PipelineBindPoint::eCompute, layout, 0, set, {});
                    }
                    cb.pushConstants(layout, vk::ShaderStageFlagBits::eCompute, 0,
                                     sizeof(Params), &params);
                    cb.dispatch((params.width + 7u) / 8u,
                                (params.height + 7u) / 8u, 1u);
                    if (upload) {
                        cb.pipelineBarrier2(barrier);
                        cb.copyBufferToImage(scratch_buffer, image_handle,
                                             vk::ImageLayout::eTransferDstOptimal, image_copy);
                    }
                });
            }
        }
        return true;
    }
};

static vk::ImageType ConvertImageType(AmdGpu::ImageType type) noexcept {
    switch (type) {
    case AmdGpu::ImageType::Color1D:
    case AmdGpu::ImageType::Color1DArray:
        return vk::ImageType::e1D;
    case AmdGpu::ImageType::Color2D:
    case AmdGpu::ImageType::Color2DMsaa:
    case AmdGpu::ImageType::Color2DArray:
        return vk::ImageType::e2D;
    case AmdGpu::ImageType::Color3D:
        return vk::ImageType::e3D;
    default:
        UNREACHABLE_MSG("Unexpected image type {}", u32(type));
    }
}

static std::pair<u32, u32> SanitizeCopyLayers(const VideoCore::ImageInfo& src_info,
                                              const VideoCore::ImageInfo& dst_info,
                                              const u32 depth) {
    const auto vk_src_type = ConvertImageType(src_info.type);
    const auto vk_dst_type = ConvertImageType(dst_info.type);

    u32 src_layers = src_info.resources.layers;
    u32 dst_layers = dst_info.resources.layers;

    // 3D images can only use 1 layer.
    if (vk_src_type == vk::ImageType::e3D && src_layers != 1) {
        LOG_WARNING(Render_Vulkan, "Coercing copy 3D source layers {} to 1.", src_layers);
        src_layers = 1;
    }
    if (vk_dst_type == vk::ImageType::e3D && dst_layers != 1) {
        LOG_WARNING(Render_Vulkan, "Coercing copy 3D destination layers {} to 1.", dst_layers);
        dst_layers = 1;
    }

    // If the image type is equal, layer count must match. Take the minimum of both.
    if (vk_src_type == vk_dst_type) {
        if (src_layers != dst_layers) {
            LOG_WARNING(Render_Vulkan,
                        "Coercing copy source layers {} and destination layers {} to minimum.",
                        src_layers, dst_layers);
            src_layers = dst_layers = std::min(src_layers, dst_layers);
        }
    } else {
        // For 2D <-> 3D copies, 2D layer count must equal 3D depth.
        if (vk_src_type == vk::ImageType::e2D && vk_dst_type == vk::ImageType::e3D &&
            src_layers != depth) {
            LOG_WARNING(Render_Vulkan,
                        "Coercing copy 2D source layers {} to 3D destination depth {}", src_layers,
                        depth);
            src_layers = depth;
        }
        if (vk_src_type == vk::ImageType::e3D && vk_dst_type == vk::ImageType::e2D &&
            dst_layers != depth) {
            LOG_WARNING(Render_Vulkan,
                        "Coercing copy 2D destination layers {} to 3D source depth {}", dst_layers,
                        depth);
            dst_layers = depth;
        }
    }

    return std::make_pair(src_layers, dst_layers);
}

static u32 BufferImageCopySize(const vk::BufferImageCopy& copy, const vk::Format pixel_format) {
    const u32 row_length = copy.bufferRowLength ? copy.bufferRowLength : copy.imageExtent.width;
    const u32 height = copy.bufferImageHeight ? copy.bufferImageHeight : copy.imageExtent.height;

    const auto block = vk::blockExtent(pixel_format);
    const u32 block_size = vk::blockSize(pixel_format);
    const u32 row_pitch = (row_length / block[0]) * block_size;
    const u32 slice_pitch = (height / block[1]) * row_pitch;

    const u32 width_in_blocks = (copy.imageExtent.width + block[0] - 1) / block[0];
    const u32 height_in_blocks = (copy.imageExtent.height + block[1] - 1) / block[1];
    const u32 num_slices = copy.imageExtent.depth * copy.imageSubresource.layerCount;

    return (num_slices - 1) * slice_pitch + (height_in_blocks - 1) * row_pitch +
           width_in_blocks * block_size;
}

Runtime::Runtime(const Instance& instance_, Scheduler& scheduler_)
    : instance{instance_}, scheduler{scheduler_}, staging_pool{instance_, scheduler_} {
    blit_helper = std::make_unique<VideoCore::BlitHelper>(instance, scheduler);

    memory_barrier.dstStageMask = vk::PipelineStageFlagBits2::eAllCommands;
    memory_barrier.dstAccessMask =
        vk::AccessFlagBits2::eMemoryRead | vk::AccessFlagBits2::eMemoryWrite;
#ifdef __ANDROID__
    // The PanVK/GoW3 hot path submits ~thousands of draws per game frame.
    // Image layout changes previously emitted an unrelated global buffer
    // barrier, even when no buffer RAW/WAR/WAW dependency was found.
    // Restrict this experiment to Mali; =0 restores the original schedule.
    const char* split = std::getenv("GOW3_MALI_IMAGE_BARRIER_SPLIT");
    split_image_buffer_barriers =
        std::getenv("GOW3_ANDROID_PORT") != nullptr &&
        instance.GetPhysicalDevice().getProperties().vendorID == 0x13B5 &&
        (!split || split[0] != '0');
    // Opt-in only until PanVK G720 A/B proves a frame-time improvement.
    // Unlike a global memory barrier, these barriers target only the
    // conflicting VkBuffer ranges. Overflow and submission fall back to
    // the original global memory barrier (no weakened dependencies).
    const char* local = std::getenv("GOW3_MALI_LOCAL_BUFFER_BARRIERS");
    mali_local_buffer_barriers = split_image_buffer_barriers && local && local[0] == '1';
    // These pipelines are already required by the exact PanVK BC/ETC2
    // and SNORM10 fallback paths. Compile before the first streamed scene.
    const char* warm = std::getenv("GOW3_MALI_PREWARM_TRANSCODE");
    if (split_image_buffer_barriers && warm && warm[0] == '1') {
        const char* etc2 = std::getenv("GOW3_MALI_BCN_TO_ETC2");
        if (!etc2 || etc2[0] != '0')
            bcn_transcode = std::make_unique<BcnTranscodeState>(instance, scheduler);
        // SNORM is retained on demand: its storage format is not universal.
    }
#endif
}

Runtime::~Runtime() = default;

void Runtime::TickFrame() {
    staging_pool.TickFrame();
}

void Runtime::CopyBuffer(const VideoCore::Buffer* src, const VideoCore::Buffer* dst,
                         std::span<const vk::BufferCopy> copies) {
    scheduler.EndRendering();

    // gow3: many regions (HLE copy shaders) are tracked as one bounding range per buffer:
    // conservative for barriers, and two tree lookups instead of two per region.
    const bool bounded = copies.size() > 4;
    u64 src_min = ~0ULL, src_max = 0, dst_min = ~0ULL, dst_max = 0;
    if (bounded) {
        for (const auto& copy : copies) {
            src_min = std::min<u64>(src_min, copy.srcOffset);
            src_max = std::max<u64>(src_max, copy.srcOffset + copy.size);
            dst_min = std::min<u64>(dst_min, copy.dstOffset);
            dst_max = std::max<u64>(dst_max, copy.dstOffset + copy.size);
        }
    }

    bool needs_flush{};
    if (bounded) {
        needs_flush = IsBufferAccessed(src, src_min, src_max - src_min) ||
                      IsBufferAccessed(dst, dst_min, dst_max - dst_min, true);
    } else {
        for (const auto& copy : copies) {
            needs_flush |= IsBufferAccessed(src, copy.srcOffset, copy.size);
            needs_flush |= IsBufferAccessed(dst, copy.dstOffset, copy.size, true);
        }
    }
    if (needs_flush) {
        FlushBarriers();
    }

    scheduler.Record([src_handle = src->Handle(), dst_handle = dst->Handle(),
                      regions = scheduler.RecordData(copies)](vk::CommandBuffer cmdbuf) {
        cmdbuf.copyBuffer(src_handle, dst_handle, regions.size(), regions.data());
    });

    if (bounded) {
        AccessBuffer(src, src_min, src_max - src_min, vk::PipelineStageFlagBits2::eCopy,
                     vk::AccessFlagBits2::eTransferRead);
        AccessBuffer(dst, dst_min, dst_max - dst_min, vk::PipelineStageFlagBits2::eCopy,
                     vk::AccessFlagBits2::eTransferWrite);
        return;
    }
    for (const auto& copy : copies) {
        AccessBuffer(src, copy.srcOffset, copy.size, vk::PipelineStageFlagBits2::eCopy,
                     vk::AccessFlagBits2::eTransferRead);
        AccessBuffer(dst, copy.dstOffset, copy.size, vk::PipelineStageFlagBits2::eCopy,
                     vk::AccessFlagBits2::eTransferWrite);
    }
}

void Runtime::FillBuffer(const VideoCore::Buffer* dst, u64 offset, u64 size, u32 value) {
    scheduler.EndRendering();

    if (IsBufferAccessed(dst, offset, size, true)) {
        FlushBarriers();
    }

    scheduler.Record([handle = dst->Handle(), offset, size, value](vk::CommandBuffer cmdbuf) {
        cmdbuf.fillBuffer(handle, offset, size, value);
    });

    AccessBuffer(dst, offset, size, vk::PipelineStageFlagBits2::eClear,
                 vk::AccessFlagBits2::eTransferWrite);
}

void Runtime::InlineData(VideoCore::Buffer* dst, u64 offset, u32 value) {
    scheduler.EndRendering();

    if (IsBufferAccessed(dst, offset, sizeof(value), true)) {
        FlushBarriers();
    }

    scheduler.Record([handle = dst->Handle(), offset, value](vk::CommandBuffer cmdbuf) {
        cmdbuf.updateBuffer(handle, offset, sizeof(value), &value);
    });

    AccessBuffer(dst, offset, sizeof(value), vk::PipelineStageFlagBits2::eCopy,
                 vk::AccessFlagBits2::eTransferWrite);
}

bool Runtime::Transit(VideoCore::Image* image, vk::ImageLayout dst_layout,
                      vk::PipelineStageFlags2 dst_stage, vk::AccessFlags2 dst_access,
                      std::optional<VideoCore::SubresourceRange> subres_range) {
    BeforeImageAccess();
    // A transfer or layout use is just as live as a FindImage/MarkFound lookup.
    // Without this stamp a clean alias could be destroyed using an older,
    // already-completed tick while this command still references its VkImage.
    image->tick_accessed_last = scheduler.CurrentTick();
    if (scene_targets) scene_targets->NativeAccess(*image, dst_access);
    const size_t prev_num_barriers = static_cast<size_t>(image_barriers.size());
    image->GetBarriers(image_barriers, dst_layout, dst_access, dst_stage, subres_range);
    return image_barriers.size() != prev_num_barriers;
}

Runtime::TransferMark::TransferMark(Runtime& runtime, const char* what,
                                    const VideoCore::Image& image) {
    profiler = GpuProfiler::Get();
    if (!profiler || !profiler->Records(&runtime.scheduler)) {
        profiler = nullptr;
        return;
    }
    resume = profiler->Current();
    const auto& info = image.info;
    const u64 key = (u64(reinterpret_cast<uintptr_t>(what)) << 20) ^
                    (u64(info.pixel_format) << 40) ^ (u64(info.size.width) << 16) ^
                    info.size.height ^ 0x7A5Full;
    profiler->Mark(key, [&] {
        return fmt::format("{} {} {}x{}", what, vk::to_string(info.pixel_format),
                           info.size.width, info.size.height);
    });
}

Runtime::TransferMark::~TransferMark() {
    if (profiler && resume) {
        profiler->Resume(resume);
    }
}

u64 Runtime::CurrentUploadBatchBytes() const {
    return texture_upload_batch_tick == scheduler.CurrentTick() ? texture_upload_batch_bytes : 0;
}

void Runtime::UploadImage(VideoCore::Image* dst, const VideoCore::Buffer* src,
                          std::span<const vk::BufferImageCopy> upload_copies) {
    // Count every actual recorded image upload, not just texture refreshes.
    // Submit only at the safe draw/dispatch boundary, never inside binding.
    const auto tick = scheduler.CurrentTick();
    if (texture_upload_batch_tick != tick) {
        texture_upload_batch_tick = tick;
        texture_upload_batch_bytes = 0;
    }
    for (const auto& copy : upload_copies)
        texture_upload_batch_bytes += BufferImageCopySize(copy, dst->info.pixel_format);
    SetBackingSamples(dst, dst->info.num_samples, false);
    scheduler.EndRendering();
    const TransferMark mark{*this, "image upload", *dst};

    bool needs_flush =
        Transit(dst, vk::ImageLayout::eTransferDstOptimal, vk::PipelineStageFlagBits2::eCopy,
                vk::AccessFlagBits2::eTransferWrite);
    for (const auto& copy : upload_copies) {
        const auto copy_size = BufferImageCopySize(copy, dst->info.pixel_format);
        needs_flush |= IsBufferAccessed(src, copy.bufferOffset, copy_size);
    }
    if (needs_flush) {
        FlushBarriers();
    }

    if (dst->transcoded_snorm2101010) {
        if (!snorm_transcode)
            snorm_transcode = std::make_unique<SnormTranscodeState>(instance, scheduler);
        ASSERT_MSG(snorm_transcode->Record(dst, src, upload_copies, staging_pool, true),
                   "Mali SNORM10 -> RGBA16_SNORM upload region is not supported");
        for (const auto& copy : upload_copies) {
            const auto copy_size = BufferImageCopySize(copy, dst->info.pixel_format);
            AccessBuffer(src, copy.bufferOffset, copy_size,
                         vk::PipelineStageFlagBits2::eComputeShader,
                         vk::AccessFlagBits2::eShaderRead);
        }
        dst->flags &= ~VideoCore::ImageFlagBits::Dirty;
        return;
    }

    if (dst->transcoded_bc_to_etc2) {
        if (!bcn_transcode) bcn_transcode = std::make_unique<BcnTranscodeState>(instance, scheduler);
        const bool recorded = bcn_transcode->Record(dst, src, upload_copies, staging_pool);
        ASSERT_MSG(recorded, "Mali BC1/BC3 -> ETC2 upload region is not supported");
        for (const auto& copy : upload_copies) {
            const auto copy_size = BufferImageCopySize(copy, dst->info.pixel_format);
            AccessBuffer(src, copy.bufferOffset, copy_size,
                         vk::PipelineStageFlagBits2::eComputeShader,
                         vk::AccessFlagBits2::eShaderRead);
        }
        dst->flags &= ~VideoCore::ImageFlagBits::Dirty;
        return;
    }

    const auto record_upload = [&](std::span<const vk::BufferImageCopy> regions) {
        u64 trace_bytes = 0;
        for (const auto& copy : regions) trace_bytes += BufferImageCopySize(copy, dst->info.pixel_format);
        scheduler.Record([this, src_handle = src->Handle(), image = dst->GetImage(),
                          addr = dst->info.guest_address, uid = dst->image_uid, trace_bytes,
                          copies = scheduler.RecordData(regions)](vk::CommandBuffer cmdbuf) {
            scheduler.TraceWork(2, addr, uid, trace_bytes);
            cmdbuf.copyBufferToImage(src_handle, image, vk::ImageLayout::eTransferDstOptimal,
                                     copies.size(), copies.data());
        });
    };
    static const bool stripes = [] {
        const char* value = std::getenv("GOW3_MALI_UPLOAD_STRIPES");
        return value && value[0] == '1';
    }();
    constexpr u64 stripe_budget = 16_MB;
    const auto block = vk::blockExtent(dst->info.pixel_format);
    const u64 texel_size = vk::blockSize(dst->info.pixel_format);
    bool needs_stripes = false;
    if (stripes && block[0] == 1 && block[1] == 1 && block[2] == 1 && texel_size)
        for (const auto& copy : upload_copies)
            needs_stripes |= copy.imageSubresource.aspectMask == vk::ImageAspectFlagBits::eColor &&
                copy.imageSubresource.layerCount == 1 && copy.imageExtent.depth == 1 &&
                copy.imageExtent.height > 1 && BufferImageCopySize(copy, dst->info.pixel_format) > stripe_budget;
    if (!needs_stripes) {
        record_upload(upload_copies);
    } else {
        for (const auto& copy : upload_copies) {
            const u64 row_texels = copy.bufferRowLength ? copy.bufferRowLength : copy.imageExtent.width;
            const u64 row_bytes = row_texels * texel_size;
            if (copy.imageSubresource.aspectMask != vk::ImageAspectFlagBits::eColor ||
                copy.imageSubresource.layerCount != 1 || copy.imageExtent.depth != 1 ||
                !row_bytes || row_bytes > stripe_budget || row_bytes % 4 ||
                BufferImageCopySize(copy, dst->info.pixel_format) <= stripe_budget) {
                record_upload(std::span{&copy, 1});
                continue;
            }
            const u32 rows_per_stripe = static_cast<u32>(stripe_budget / row_bytes);
            for (u32 y = 0; y < copy.imageExtent.height; ) {
                auto stripe = copy;
                stripe.bufferOffset += u64(y) * row_bytes;
                stripe.imageOffset.y += static_cast<s32>(y);
                stripe.imageExtent.height = std::min(rows_per_stripe, copy.imageExtent.height - y);
                // Single layer/depth only, so no layer stride is changed.
                record_upload(std::span<const vk::BufferImageCopy>{&stripe, 1});
                y += stripe.imageExtent.height;
            }
            static u64 split_uploads = 0;
            if (++split_uploads <= 8 || (split_uploads & 255u) == 0)
                std::printf("GOW3_MALI_UPLOAD_STRIPES count=%llu bytes=%u\n",
                    (unsigned long long)split_uploads, BufferImageCopySize(copy, dst->info.pixel_format));
        }
    }

    for (const auto& copy : upload_copies) {
        const auto copy_size = BufferImageCopySize(copy, dst->info.pixel_format);
        AccessBuffer(src, copy.bufferOffset, copy_size, vk::PipelineStageFlagBits2::eCopy,
                     vk::AccessFlagBits2::eTransferRead);
    }

    dst->flags &= ~VideoCore::ImageFlagBits::Dirty;
}

void Runtime::CopyAliasImage(VideoCore::Image* src, VideoCore::Image* dst,
                             const vk::Extent3D& extent) {
    if (src->transcoded_snorm2101010 != dst->transcoded_snorm2101010) {
        // Guest aliases may reference a packed 4-byte SNORM10 image while
        // the physical source is RGBA16_SNORM (8 bytes). VkCmdCopyImage is
        // invalid for mismatched texel block sizes. Keep the EXACT supplied
        // alias extent and transfer guest-format bytes through the device-
        // local tick-safe staging buffer without a CPU wait or conversion.
        ASSERT_MSG(extent.depth == 1 && src->info.resources.layers == 1 &&
                       dst->info.resources.layers == 1 && src->info.num_samples == 1 &&
                       dst->info.num_samples == 1 &&
                       vk::blockSize(src->info.pixel_format) == 4 &&
                       vk::blockSize(dst->info.pixel_format) == 4,
                   "Unsupported mixed SNORM10 alias extent");
        const auto scratch = staging_pool.Request(
            u64(extent.width) * extent.height * 4u, VideoCore::MemoryType::DeviceLocal, 16);
        const vk::BufferImageCopy region{
            .bufferOffset = scratch.offset,
            .bufferRowLength = 0,
            .bufferImageHeight = 0,
            .imageSubresource{.aspectMask = vk::ImageAspectFlagBits::eColor,
                              .mipLevel = 0, .baseArrayLayer = 0, .layerCount = 1},
            .imageOffset = {0, 0, 0},
            .imageExtent = extent,
        };
        DownloadImage(src, scratch.buffer, std::span{&region, 1});
        UploadImage(dst, scratch.buffer, std::span{&region, 1});
        return;
    }
    SetBackingSamples(src, src->info.num_samples);
    SetBackingSamples(dst, dst->info.num_samples);
    scheduler.EndRendering();
    const TransferMark mark{*this, "image alias copy", *dst};
    const u32 layers = std::min(src->info.resources.layers, dst->info.resources.layers);
    const vk::ImageCopy region{
        .srcSubresource{.aspectMask = vk::ImageAspectFlagBits::eColor, .layerCount = layers},
        .dstSubresource{.aspectMask = vk::ImageAspectFlagBits::eColor, .layerCount = layers},
        .extent = extent,
    };
    bool needs_flush =
        Transit(src, vk::ImageLayout::eTransferSrcOptimal, vk::PipelineStageFlagBits2::eCopy,
                vk::AccessFlagBits2::eTransferRead);
    needs_flush |= Transit(dst, vk::ImageLayout::eTransferDstOptimal,
                           vk::PipelineStageFlagBits2::eCopy, vk::AccessFlagBits2::eTransferWrite);
    if (needs_flush) {
        FlushBarriers();
    }
    scheduler.Record([src_image = src->GetImage(), dst_image = dst->GetImage(),
                      region](vk::CommandBuffer cmdbuf) {
        cmdbuf.copyImage(src_image, vk::ImageLayout::eTransferSrcOptimal, dst_image,
                         vk::ImageLayout::eTransferDstOptimal, region);
    });
}

void Runtime::DownloadImage(VideoCore::Image* src, const VideoCore::Buffer* dst,
                            std::span<const vk::BufferImageCopy> download_copies) {
    SetBackingSamples(src, src->info.num_samples);
    scheduler.EndRendering();
    const TransferMark mark{*this, "image download", *src};

    bool needs_flush =
        Transit(src, vk::ImageLayout::eTransferSrcOptimal, vk::PipelineStageFlagBits2::eCopy,
                vk::AccessFlagBits2::eTransferRead);
    for (const auto& copy : download_copies) {
        const auto copy_size = BufferImageCopySize(copy, src->info.pixel_format);
        needs_flush |= IsBufferAccessed(dst, copy.bufferOffset, copy_size, true);
    }
    if (needs_flush) {
        FlushBarriers();
    }

    if (src->transcoded_snorm2101010) {
        if (!snorm_transcode)
            snorm_transcode = std::make_unique<SnormTranscodeState>(instance, scheduler);
        ASSERT_MSG(snorm_transcode->Record(src, dst, download_copies, staging_pool, false),
                   "Mali RGBA16_SNORM -> SNORM10 download region is not supported");
        for (const auto& copy : download_copies) {
            const auto copy_size = BufferImageCopySize(copy, src->info.pixel_format);
            AccessBuffer(dst, copy.bufferOffset, copy_size,
                         vk::PipelineStageFlagBits2::eComputeShader,
                         vk::AccessFlagBits2::eShaderWrite);
        }
        return;
    }

    u64 trace_bytes = 0;
    for (const auto& copy : download_copies) trace_bytes += BufferImageCopySize(copy, src->info.pixel_format);
    scheduler.Record([this, image = src->GetImage(), buffer = dst->Handle(),
                      addr = src->info.guest_address, uid = src->image_uid, trace_bytes,
                      regions = scheduler.RecordData(download_copies)](vk::CommandBuffer cmdbuf) {
        scheduler.TraceWork(3, addr, uid, trace_bytes);
        cmdbuf.copyImageToBuffer(image, vk::ImageLayout::eTransferSrcOptimal, buffer,
                                 regions.size(), regions.data());
    });

    for (const auto& copy : download_copies) {
        const auto copy_size = BufferImageCopySize(copy, src->info.pixel_format);
        AccessBuffer(dst, copy.bufferOffset, copy_size, vk::PipelineStageFlagBits2::eCopy,
                     vk::AccessFlagBits2::eTransferWrite);
    }
}

void Runtime::CopyImage(VideoCore::Image* src, VideoCore::Image* dst) {
    const u32 num_mips = std::min(src->info.resources.levels, dst->info.resources.levels);
    // Unlike BC1->ETC2, SNORM10 changes the host bytes-per-pixel from 4
    // to 8. VkCmdCopyImage across these two physical formats is invalid.
    // Preserve PS4 guest bytes by downloading into the existing tick-safe GPU
    // staging arena, then uploading through the appropriate conversion. The
    // Runtime buffer hazards order the two operations; no CPU wait is needed.
    if (src->transcoded_snorm2101010 != dst->transcoded_snorm2101010) {
        ASSERT_MSG(src->info.num_samples == 1 && dst->info.num_samples == 1 &&
                       src->info.resources.layers == 1 && dst->info.resources.layers == 1 &&
                       ConvertImageType(src->info.type) == vk::ImageType::e2D &&
                       ConvertImageType(dst->info.type) == vk::ImageType::e2D &&
                       vk::blockSize(src->info.pixel_format) == 4 &&
                       vk::blockSize(dst->info.pixel_format) == 4,
                   "SNORM10 mixed physical image copy needs a 4-byte PS4 2D image pair");
        for (u32 mip = 0; mip < num_mips; ++mip) {
            const u32 width = std::min(std::max(src->info.size.width >> mip, 1u),
                                       std::max(dst->info.size.width >> mip, 1u));
            const u32 height = std::min(std::max(src->info.size.height >> mip, 1u),
                                        std::max(dst->info.size.height >> mip, 1u));
            const auto staging = staging_pool.Request(
                u64(width) * height * 4u, VideoCore::MemoryType::DeviceLocal, 16);
            const vk::BufferImageCopy region{
                .bufferOffset = staging.offset,
                .bufferRowLength = 0,
                .bufferImageHeight = 0,
                .imageSubresource{.aspectMask = vk::ImageAspectFlagBits::eColor,
                                  .mipLevel = mip, .baseArrayLayer = 0, .layerCount = 1},
                .imageOffset = {0, 0, 0},
                .imageExtent = {width, height, 1},
            };
            DownloadImage(src, staging.buffer, std::span{&region, 1});
            UploadImage(dst, staging.buffer, std::span{&region, 1});
        }
        dst->flags |= (src->flags & VideoCore::ImageFlagBits::GpuModified);
        dst->flags &= ~VideoCore::ImageFlagBits::Dirty;
        return;
    }

    // Format mismatch warning (safe but useful)
    if (src->info.pixel_format != dst->info.pixel_format) {
        LOG_DEBUG(Render_Vulkan,
                  "Copy between different formats: src={}, dst={}. "
                  "Result may be undefined.",
                  vk::to_string(src->info.pixel_format), vk::to_string(dst->info.pixel_format));
    }

    const u32 base_width = src->info.size.width;
    const u32 base_height = src->info.size.height;
    const u32 base_depth =
        dst->info.type == AmdGpu::ImageType::Color3D ? dst->info.size.depth : src->info.size.depth;

    // Match sample count before copying
    SetBackingSamples(dst, dst->info.num_samples, false);
    SetBackingSamples(src, src->info.num_samples);

    boost::container::small_vector<vk::ImageCopy, 8> regions;

    const vk::ImageAspectFlags src_aspect = src->aspect_mask & ~vk::ImageAspectFlagBits::eStencil;
    const vk::ImageAspectFlags dst_aspect = dst->aspect_mask & ~vk::ImageAspectFlagBits::eStencil;

    const bool src_is_2d = ConvertImageType(src->info.type) == vk::ImageType::e2D;
    const bool src_is_3d = ConvertImageType(src->info.type) == vk::ImageType::e3D;

    const bool dst_is_2d = ConvertImageType(dst->info.type) == vk::ImageType::e2D;
    const bool dst_is_3d = ConvertImageType(dst->info.type) == vk::ImageType::e3D;

    const bool is_2d_to_3d = src_is_2d && dst_is_3d;
    const bool is_3d_to_2d = src_is_3d && dst_is_2d;
    const bool is_same_type = !is_2d_to_3d && !is_3d_to_2d;

    for (u32 mip = 0; mip < num_mips; ++mip) {
        const u32 mip_w = std::max(base_width >> mip, 1u);
        const u32 mip_h = std::max(base_height >> mip, 1u);
        const u32 mip_d = std::max(base_depth >> mip, 1u);

        const auto [src_layers, dst_layers] = SanitizeCopyLayers(src->info, dst->info, mip_d);

        vk::ImageCopy region{};
        region.srcSubresource.aspectMask = src_aspect;
        region.srcSubresource.mipLevel = mip;
        region.srcSubresource.baseArrayLayer = 0;
        region.dstSubresource.aspectMask = dst_aspect;
        region.dstSubresource.mipLevel = mip;
        region.dstSubresource.baseArrayLayer = 0;

        if (is_same_type) {
            // 2D->2D OR 3D->3D
            if (src_is_3d) {
                // 3D images must use layerCount=1
                region.srcSubresource.layerCount = 1;
                region.dstSubresource.layerCount = 1;
                region.extent = vk::Extent3D(mip_w, mip_h, mip_d);
            } else {
                // Array images
                const u32 copy_layers = std::min(src_layers, dst_layers);
                region.srcSubresource.layerCount = copy_layers;
                region.dstSubresource.layerCount = copy_layers;
                region.extent = vk::Extent3D(mip_w, mip_h, 1);
            }
        } else if (is_2d_to_3d) {
            // 2D array -> 3D volume
            region.srcSubresource.layerCount = src_layers;
            region.dstSubresource.layerCount = 1;
            region.extent = vk::Extent3D(mip_w, mip_h, src_layers);
        } else if (is_3d_to_2d) {
            // 3D volume -> 2D array
            region.srcSubresource.layerCount = 1;
            region.dstSubresource.layerCount = dst_layers;
            region.extent = vk::Extent3D(mip_w, mip_h, dst_layers);
        }

        regions.push_back(region);
    }

    scheduler.EndRendering();

    bool needs_flush =
        Transit(src, vk::ImageLayout::eTransferSrcOptimal, vk::PipelineStageFlagBits2::eCopy,
                vk::AccessFlagBits2::eTransferRead);
    needs_flush |= Transit(dst, vk::ImageLayout::eTransferDstOptimal,
                           vk::PipelineStageFlagBits2::eCopy, vk::AccessFlagBits2::eTransferWrite);
    if (needs_flush) {
        FlushBarriers();
    }

    scheduler.Record([src_image = src->GetImage(), dst_image = dst->GetImage(),
                      regions](vk::CommandBuffer cmdbuf) {
        cmdbuf.copyImage(src_image, vk::ImageLayout::eTransferSrcOptimal, dst_image,
                         vk::ImageLayout::eTransferDstOptimal, regions);
    });

    dst->flags |= (src->flags & VideoCore::ImageFlagBits::GpuModified);
    dst->flags &= ~VideoCore::ImageFlagBits::Dirty;
}

void Runtime::CopyImageWithBuffer(VideoCore::Image* src, VideoCore::Image* dst,
                                  const VideoCore::Buffer* buffer, u64 offset) {
    const u32 num_mips = std::min(src->info.resources.levels, dst->info.resources.levels);
    const u32 num_layers = std::min(src->info.resources.layers, dst->info.resources.layers);
    ASSERT(src->info.resources.layers == dst->info.resources.layers && num_mips == 1);

    SetBackingSamples(dst, dst->info.num_samples, false);
    SetBackingSamples(src, src->info.num_samples);

    vk::BufferImageCopy buffer_copy = {
        .bufferOffset = offset,
        .bufferRowLength = 0,
        .bufferImageHeight = 0,
        .imageSubresource{
            .aspectMask = src->aspect_mask & ~vk::ImageAspectFlagBits::eStencil,
            .mipLevel = 0u,
            .baseArrayLayer = 0,
            .layerCount = num_layers,
        },
        .imageOffset = {0, 0, 0},
        .imageExtent = {src->info.size.width, src->info.size.height, src->info.size.depth},
    };
    // Use the *allocated Vulkan format*, not the PS4 descriptor format.
    // PanVK cannot allocate D16S8 and legitimately backs it with D24S8 or
    // D32S8; sizing the intermediate transfer using the guest D16S8 format
    // underestimates the actual Vulkan depth-aspect transfer and can truncate
    // image data or cause read/write overlap in the staging arena.
    const vk::Format physical_source_format = src->backing->image.image_ci.format;
    const auto copy_size = BufferImageCopySize(buffer_copy, physical_source_format);
    if (instance.GetPhysicalDevice().getProperties().vendorID == 0x13B5 &&
        physical_source_format != src->info.pixel_format) {
        static u32 mali_depth_fallback_copies = 0;
        if (mali_depth_fallback_copies++ < 8) {
            LOG_WARNING(Render_Vulkan,
                        "PanVK image bridge: guest format {} uses physical {} copy size {}",
                        vk::to_string(src->info.pixel_format),
                        vk::to_string(physical_source_format), copy_size);
        }
    }

    scheduler.EndRendering();

    bool needs_flush =
        Transit(src, vk::ImageLayout::eTransferSrcOptimal, vk::PipelineStageFlagBits2::eCopy,
                vk::AccessFlagBits2::eTransferRead);
    needs_flush |= Transit(dst, vk::ImageLayout::eTransferDstOptimal,
                           vk::PipelineStageFlagBits2::eCopy, vk::AccessFlagBits2::eTransferWrite);
    needs_flush |= IsBufferAccessed(buffer, offset, copy_size);
    if (needs_flush) {
        FlushBarriers();
    }

    const auto download_copy = buffer_copy;
    buffer_copy.imageSubresource.aspectMask = dst->aspect_mask & ~vk::ImageAspectFlagBits::eStencil;
    scheduler.Record([src_image = src->GetImage(), dst_image = dst->GetImage(),
                      handle = buffer->Handle(), download_copy,
                      upload_copy = buffer_copy](vk::CommandBuffer cmdbuf) {
        cmdbuf.copyImageToBuffer(src_image, vk::ImageLayout::eTransferSrcOptimal, handle,
                                 download_copy);
        const vk::MemoryBarrier2 post_copy_barrier = {
            .srcStageMask = vk::PipelineStageFlagBits2::eCopy,
            .srcAccessMask = vk::AccessFlagBits2::eTransferWrite,
            .dstStageMask = vk::PipelineStageFlagBits2::eCopy,
            .dstAccessMask = vk::AccessFlagBits2::eTransferRead,
        };
        cmdbuf.pipelineBarrier2(vk::DependencyInfo{
            .dependencyFlags = vk::DependencyFlagBits::eByRegion,
            .memoryBarrierCount = 1u,
            .pMemoryBarriers = &post_copy_barrier,
        });
        cmdbuf.copyBufferToImage(handle, dst_image, vk::ImageLayout::eTransferDstOptimal,
                                 upload_copy);
    });

    dst->flags |= (src->flags & VideoCore::ImageFlagBits::GpuModified);
    dst->flags &= ~VideoCore::ImageFlagBits::Dirty;
}

void Runtime::CopyMip(VideoCore::Image* src, VideoCore::Image* dst, u32 mip, u32 slice) {
    const auto dst_dim = dst->info.props.is_block ? 2 : 0;
    const auto mip_block_w = std::max(dst->info.size.width >> (mip + dst_dim), 1u);
    const auto mip_block_h = std::max(dst->info.size.height >> (mip + dst_dim), 1u);
    const auto mip_block_p = std::max(dst->info.mips_layout[mip].pitch >> dst_dim, 1u);

    const auto src_dim = src->info.props.is_block ? 2 : 0;
    ASSERT(mip_block_w == (src->info.size.width >> src_dim));
    ASSERT(mip_block_h == (src->info.size.height >> src_dim));
    ASSERT(mip_block_p == (src->info.pitch >> src_dim));

    const auto [src_layers, dst_layers] =
        SanitizeCopyLayers(src->info, dst->info, src->info.size.depth);

    const vk::ImageCopy image_copy{
        .srcSubresource{
            .aspectMask = src->aspect_mask,
            .mipLevel = 0,
            .baseArrayLayer = 0,
            .layerCount = src_layers,
        },
        .dstSubresource{
            .aspectMask = src->aspect_mask,
            .mipLevel = mip,
            .baseArrayLayer = slice,
            .layerCount = dst_layers,
        },
        .extent = {src->info.size.width, src->info.size.height, src->info.size.depth},
    };

    SetBackingSamples(dst, dst->info.num_samples);
    SetBackingSamples(src, src->info.num_samples);

    scheduler.EndRendering();

    bool needs_flush =
        Transit(src, vk::ImageLayout::eTransferSrcOptimal, vk::PipelineStageFlagBits2::eCopy,
                vk::AccessFlagBits2::eTransferRead);
    needs_flush |= Transit(dst, vk::ImageLayout::eTransferDstOptimal,
                           vk::PipelineStageFlagBits2::eCopy, vk::AccessFlagBits2::eTransferWrite);
    if (needs_flush) {
        FlushBarriers();
    }

    scheduler.Record([src_image = src->GetImage(), dst_image = dst->GetImage(),
                      image_copy](vk::CommandBuffer cmdbuf) {
        cmdbuf.copyImage(src_image, vk::ImageLayout::eTransferSrcOptimal, dst_image,
                         vk::ImageLayout::eTransferDstOptimal, image_copy);
    });

    dst->flags |= (src->flags & VideoCore::ImageFlagBits::GpuModified);
    dst->flags &= ~VideoCore::ImageFlagBits::Dirty;
}

void Runtime::CopyColorAndDepth(VideoCore::Image* src, VideoCore::Image* dst) {
    if (src->info.num_samples == 1 && dst->info.num_samples == 1) {
        if (instance.IsMaintenance8Supported() ||
            src->info.props.is_depth == dst->info.props.is_depth) {
            CopyImage(src, dst);
        } else {
            // Perform depth from/to color copy using the intermediate copy buffer.
            static constexpr size_t COPY_BUFFER_SIZE = 128_MB;
            const auto copy_ref =
                staging_pool.Request(COPY_BUFFER_SIZE, VideoCore::MemoryType::DeviceLocal);
            CopyImageWithBuffer(src, dst, copy_ref.buffer, copy_ref.offset);
        }
    } else if (src->info.num_samples == 1 && dst->info.num_samples > 1 &&
               dst->info.props.is_depth) {
        // Perform a rendering pass to transfer the channels of source as samples in dest.
        bool needs_flush =
            Transit(src, vk::ImageLayout::eShaderReadOnlyOptimal,
                    vk::PipelineStageFlagBits2::eFragmentShader, vk::AccessFlagBits2::eShaderRead);
        needs_flush |= Transit(dst, vk::ImageLayout::eDepthStencilAttachmentOptimal,
                               vk::PipelineStageFlagBits2::eEarlyFragmentTests |
                                   vk::PipelineStageFlagBits2::eLateFragmentTests,
                               vk::AccessFlagBits2::eDepthStencilAttachmentWrite);
        if (needs_flush) {
            FlushBarriers();
        }

        blit_helper->ReinterpretColorAsMsDepth(
            dst->info.size.width, dst->info.size.height, dst->info.num_samples,
            src->info.pixel_format, dst->info.pixel_format, src->GetImage(), dst->GetImage());
    } else {
        LOG_WARNING(Render_Vulkan, "Unimplemented depth overlap copy");
    }
}

void Runtime::CopyDepthStencil(VideoCore::Image* src, VideoCore::Image* dst,
                               const VideoCore::SubresourceRange& sub_range) {
    scheduler.EndRendering();

    bool needs_flush =
        Transit(src, vk::ImageLayout::eTransferSrcOptimal, vk::PipelineStageFlagBits2::eCopy,
                vk::AccessFlagBits2::eTransferRead);
    needs_flush |= Transit(dst, vk::ImageLayout::eTransferDstOptimal,
                           vk::PipelineStageFlagBits2::eCopy, vk::AccessFlagBits2::eTransferWrite);
    if (needs_flush) {
        FlushBarriers();
    }

    const auto aspect_mask = src->aspect_mask & dst->aspect_mask;

    const vk::ImageCopy region = {
        .srcSubresource{
            .aspectMask = aspect_mask,
            .mipLevel = 0,
            .baseArrayLayer = sub_range.base.layer,
            .layerCount = sub_range.extent.layers,
        },
        .srcOffset = {0, 0, 0},
        .dstSubresource{
            .aspectMask = aspect_mask,
            .mipLevel = 0,
            .baseArrayLayer = sub_range.base.layer,
            .layerCount = sub_range.extent.layers,
        },
        .dstOffset = {0, 0, 0},
        .extent = {dst->info.size.width, dst->info.size.height, 1},
    };

    scheduler.Record([src_image = src->GetImage(), dst_image = dst->GetImage(),
                      region](vk::CommandBuffer cmdbuf) {
        cmdbuf.copyImage(src_image, vk::ImageLayout::eTransferSrcOptimal, dst_image,
                         vk::ImageLayout::eTransferDstOptimal, region);
    });

    dst->flags |= VideoCore::ImageFlagBits::GpuModified;
    dst->flags &= ~VideoCore::ImageFlagBits::Dirty;
}

void Runtime::ResolveImage(VideoCore::Image* src, VideoCore::Image* dst,
                           const VideoCore::SubresourceRange& src_range,
                           const VideoCore::SubresourceRange& dst_range) {
    SetBackingSamples(dst, 1, false);
    scheduler.EndRendering();

    const bool needs_resolve = src->backing->num_samples != 1;
    const auto dst_stage =
        needs_resolve ? vk::PipelineStageFlagBits2::eResolve : vk::PipelineStageFlagBits2::eCopy;

    bool needs_flush = Transit(src, vk::ImageLayout::eTransferSrcOptimal, dst_stage,
                               vk::AccessFlagBits2::eTransferRead);
    needs_flush |= Transit(dst, vk::ImageLayout::eTransferDstOptimal, dst_stage,
                           vk::AccessFlagBits2::eTransferWrite);
    if (needs_flush) {
        FlushBarriers();
    }

    const auto [src_layers, dst_layers] = SanitizeCopyLayers(src->info, dst->info, 1);
    if (!needs_resolve) {
        const vk::ImageCopy region = {
            .srcSubresource{
                .aspectMask = vk::ImageAspectFlagBits::eColor,
                .mipLevel = 0,
                .baseArrayLayer = src_range.base.layer,
                .layerCount = src_layers,
            },
            .srcOffset = {0, 0, 0},
            .dstSubresource{
                .aspectMask = vk::ImageAspectFlagBits::eColor,
                .mipLevel = 0,
                .baseArrayLayer = dst_range.base.layer,
                .layerCount = dst_layers,
            },
            .dstOffset = {0, 0, 0},
            .extent = {src->info.size.width, src->info.size.height, 1},
        };
        scheduler.Record([src_image = src->GetImage(), dst_image = dst->GetImage(),
                          region](vk::CommandBuffer cmdbuf) {
            cmdbuf.copyImage(src_image, vk::ImageLayout::eTransferSrcOptimal, dst_image,
                             vk::ImageLayout::eTransferDstOptimal, region);
        });
    } else {
        const vk::ImageResolve region = {
            .srcSubresource{
                .aspectMask = vk::ImageAspectFlagBits::eColor,
                .mipLevel = 0,
                .baseArrayLayer = src_range.base.layer,
                .layerCount = src_layers,
            },
            .srcOffset = {0, 0, 0},
            .dstSubresource{
                .aspectMask = vk::ImageAspectFlagBits::eColor,
                .mipLevel = 0,
                .baseArrayLayer = dst_range.base.layer,
                .layerCount = dst_layers,
            },
            .dstOffset = {0, 0, 0},
            .extent = {src->info.size.width, src->info.size.height, 1},
        };
        scheduler.Record([src_image = src->GetImage(), dst_image = dst->GetImage(),
                          region](vk::CommandBuffer cmdbuf) {
            cmdbuf.resolveImage(src_image, vk::ImageLayout::eTransferSrcOptimal, dst_image,
                                vk::ImageLayout::eTransferDstOptimal, region);
        });
    }

    dst->flags |= VideoCore::ImageFlagBits::GpuModified;
    dst->flags &= ~VideoCore::ImageFlagBits::Dirty;
}

void Runtime::ClearImage(VideoCore::Image* dst, const VideoCore::SubresourceRange& range,
                         const vk::ClearValue& clear_value) {
    scheduler.EndRendering();

    const bool needs_flush =
        Transit(dst, vk::ImageLayout::eTransferDstOptimal, vk::PipelineStageFlagBits2::eClear,
                vk::AccessFlagBits2::eTransferWrite, range);
    if (needs_flush) {
        FlushBarriers();
    }

    const vk::ImageSubresourceRange vk_range = {
        .aspectMask = vk::ImageAspectFlagBits::eColor,
        .baseMipLevel = range.base.level,
        .levelCount = range.extent.levels,
        .baseArrayLayer = range.base.layer,
        .layerCount = range.extent.layers,
    };
    scheduler.Record([image = dst->GetImage(), color = clear_value.color,
                      vk_range](vk::CommandBuffer cmdbuf) {
        cmdbuf.clearColorImage(image, vk::ImageLayout::eTransferDstOptimal, color, vk_range);
    });

    dst->flags |= VideoCore::ImageFlagBits::GpuModified;
    dst->flags &= ~VideoCore::ImageFlagBits::Dirty;
}

void Runtime::SetBackingSamples(VideoCore::Image* image, u32 num_samples, bool copy_backing) {
    BeforeImageAccess();
    image->tick_accessed_last = scheduler.CurrentTick();
    auto& backing = image->backing;
    auto& backing_images = image->backing_images;
    const auto& info = image->info;
    if (!backing || backing->num_samples == num_samples) {
        return;
    }
    ASSERT_MSG(!image->info.props.is_depth, "Swapping samples is only valid for color images");
    VideoCore::Image::BackingImage* new_backing;
    auto it = std::ranges::find(backing_images, num_samples,
                                &VideoCore::Image::BackingImage::num_samples);
    if (it == backing_images.end()) {
        auto new_image_ci = backing->image.image_ci;
        new_image_ci.samples = LiverpoolToVK::NumSamples(num_samples, image->supported_samples);

        new_backing = &backing_images.emplace_back();
        new_backing->num_samples = num_samples;
        new_backing->image = VideoCore::UniqueImage{instance.GetDevice(), instance.GetAllocator()};
        new_backing->image.Create(new_image_ci);

        Vulkan::SetObjectName(instance.GetDevice(), new_backing->image.image,
                              "Image {}x{}x{} {} {} {:#x}:{:#x} L:{} M:{} S:{} (backing)",
                              info.size.width, info.size.height, info.size.depth,
                              AmdGpu::NameOf(info.tile_mode), vk::to_string(info.pixel_format),
                              info.guest_address, info.guest_size, info.resources.layers,
                              info.resources.levels, num_samples);
    } else {
        new_backing = std::addressof(*it);
    }

    if (copy_backing) {
        scheduler.EndRendering();
        ASSERT(image->info.resources.levels == 1 && image->info.resources.layers == 1);

        // Transition current backing to shader read layout
        Transit(image, vk::ImageLayout::eShaderReadOnlyOptimal,
                vk::PipelineStageFlagBits2::eFragmentShader, vk::AccessFlagBits2::eShaderRead);

        // Transition dest backing to color attachment layout, not caring of previous contents
        constexpr auto dst_stage = vk::PipelineStageFlagBits2::eColorAttachmentOutput;
        constexpr auto dst_access =
            vk::AccessFlagBits2::eColorAttachmentRead | vk::AccessFlagBits2::eColorAttachmentWrite;
        constexpr auto dst_layout = vk::ImageLayout::eColorAttachmentOptimal;
        image_barriers.push_back(vk::ImageMemoryBarrier2{
            .srcStageMask = vk::PipelineStageFlagBits2::eAllCommands,
            .srcAccessMask = vk::AccessFlagBits2::eMemoryRead | vk::AccessFlagBits2::eMemoryWrite,
            .dstStageMask = dst_stage,
            .dstAccessMask = dst_access,
            .oldLayout = vk::ImageLayout::eUndefined,
            .newLayout = dst_layout,
            .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
            .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
            .image = new_backing->image,
            .subresourceRange{
                .aspectMask = image->aspect_mask,
                .baseMipLevel = 0,
                .levelCount = 1,
                .baseArrayLayer = 0,
                .layerCount = image->info.resources.layers,
            },
        });
        FlushBarriers();

        // Copy between ms and non ms backing images
        blit_helper->CopyBetweenMsImages(
            info.size.width, info.size.height, new_backing->num_samples, info.pixel_format,
            backing->num_samples > 1, backing->image, new_backing->image);

        // Update current layout in tracker to new backings layout
        new_backing->state.layout = dst_layout;
        new_backing->state.access_mask = dst_access;
        new_backing->state.pl_stage = dst_stage;
    }

    backing = new_backing;
}

bool Runtime::IsBufferAccessed(const VideoCore::Buffer* handle, u64 offset, u64 size,
                               bool check_read_access) {
    const AddressRange range = {
        .resource = reinterpret_cast<u64>(handle),
        .range_start = offset,
        .range_end = offset + size - 1,
    };
    bool has_access = barrier_tracker.FindRange(range, Access::Write);
    if (check_read_access && !has_access) {
        has_access |= barrier_tracker.FindRange(range, Access::Read);
    }
    // Includes WAR execution dependencies: read->write is not harmless.
    // The old global memory barrier must still be emitted for any overlapping
    // writer or prior read when the next operation writes the same range.
    buffer_hazard_pending |= has_access;
    if (has_access && mali_local_buffer_barriers && !pending_mali_buffer_barriers.Overflow()) {
        pending_mali_buffer_barriers.Add(std::bit_cast<u64>(handle->Handle()), offset, size);
    }
    return has_access;
}

void Runtime::AccessBuffer(const VideoCore::Buffer* handle, u64 offset, u64 size,
                           vk::PipelineStageFlags2 src_stage, vk::AccessFlags2 src_access) {
    AddressRange range = {
        .resource = reinterpret_cast<u64>(handle),
        .range_start = offset,
        .range_end = offset + size - 1,
    };

    constexpr static vk::AccessFlags2 READ_MASK =
        vk::AccessFlagBits2::eIndexRead | vk::AccessFlagBits2::eVertexAttributeRead |
        vk::AccessFlagBits2::eUniformRead | vk::AccessFlagBits2::eShaderRead |
        vk::AccessFlagBits2::eColorAttachmentRead |
        vk::AccessFlagBits2::eDepthStencilAttachmentRead | vk::AccessFlagBits2::eTransferRead |
        vk::AccessFlagBits2::eMemoryRead;

    constexpr static vk::AccessFlags2 WRITE_MASK =
        vk::AccessFlagBits2::eShaderWrite | vk::AccessFlagBits2::eColorAttachmentWrite |
        vk::AccessFlagBits2::eDepthStencilAttachmentWrite | vk::AccessFlagBits2::eTransferWrite |
        vk::AccessFlagBits2::eMemoryWrite | vk::AccessFlagBits2::eTransformFeedbackWriteEXT;

    // When the tracker is retired on a buffer hazard, it retires *every*
    // previously recorded access, not just the range that caused the flush.
    // Therefore local VkBuffer barriers must cover ALL pending resources;
    // otherwise a later draw can miss a dependency on another buffer.
    // Too many distinct ranges conservatively fall back to the original
    // global memory barrier via MaliBufferBarrierRegions::Overflow().
    if (mali_local_buffer_barriers && !pending_mali_buffer_barriers.Overflow()) {
        pending_mali_buffer_barriers.Add(std::bit_cast<u64>(handle->Handle()),
                                         offset, size);
    }

    // gow3: reads are tracked at 4 KiB granularity. Constant data comes from ring allocations
    // at a new offset every draw; rounded, they land in ranges already present and the
    // insert returns early instead of growing the tree until the next barrier flush.
    // Wider read ranges only add barriers, never drop one.
    if (!(src_access & WRITE_MASK) && !Gow3Toggle::Disabled(Gow3Toggle::CoarseReadTracking)) {
        range.range_start &= ~u64{0xFFF};
        range.range_end |= 0xFFF;
    }
    const auto insert = [&](Access access) {
        if (Gow3Toggle::Disabled(Gow3Toggle::AccessMemo)) {
            barrier_tracker.InsertRange(range, access);
            return;
        }
        u64 hash = range.resource ^ range.range_start * 0x9E3779B97F4A7C15ull ^
                   range.range_end << 13 ^ u64(access) << 61;
        hash = (hash ^ hash >> 31) * 0xFF51AFD7ED558CCDull;
        auto& memo = access_memo[(hash ^ hash >> 29) % access_memo.size()];
        if (memo.epoch == access_epoch && memo.resource == range.resource &&
            memo.start == range.range_start && memo.end == range.range_end &&
            memo.access == u32(access)) {
            return;
        }
        barrier_tracker.InsertRange(range, access);
        memo = {range.resource, range.range_start, range.range_end, access_epoch, u32(access)};
    };
    if (src_access & WRITE_MASK) {
        insert(Access::Write);
    }
    if (src_access & READ_MASK) {
        insert(Access::Read);
    }

    memory_barrier.srcStageMask |= src_stage;
    memory_barrier.srcAccessMask |= src_access & WRITE_MASK;
}

void Runtime::FlushBarriers(bool force_buffer_barrier) {
    BeforeImageAccess();
    const auto decision = DecideBarrierFlush(
        split_image_buffer_barriers, buffer_hazard_pending, force_buffer_barrier,
        bool(memory_barrier.srcStageMask), !image_barriers.empty());
    if (!decision.has_work()) {
        return;
    }

    // An image-only dependency needs only VkImageMemoryBarrier2 entries.
    // For a true buffer hazard on Mali, optionally scope the memory
    // dependency to the exact VkBuffer objects/ranges that conflicted.
    // No range is dropped: overflow, invalid offsets, and queue-submit
    // force the original global VkMemoryBarrier2 instead.
    const bool local_buffers = mali_local_buffer_barriers && decision.emit_memory &&
        buffer_hazard_pending && !force_buffer_barrier &&
        !pending_mali_buffer_barriers.Overflow() &&
        pending_mali_buffer_barriers.Count() > 0;
    std::array<vk::BufferMemoryBarrier2, MaliBufferBarrierRegions::Max> local_buffer_info{};
    u32 local_buffer_count = 0;
    if (local_buffers) {
        for (std::size_t i = 0; i < pending_mali_buffer_barriers.Count(); ++i) {
            const auto& region = pending_mali_buffer_barriers[i];
            local_buffer_info[local_buffer_count++] = {
                .srcStageMask = memory_barrier.srcStageMask,
                .srcAccessMask = memory_barrier.srcAccessMask,
                .dstStageMask = memory_barrier.dstStageMask,
                .dstAccessMask = memory_barrier.dstAccessMask,
                .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
                .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
                .buffer = std::bit_cast<vk::Buffer>(region.buffer),
                .offset = region.offset,
                .size = region.size,
            };
        }
    }
    MaliPerfStats::CountBarrierFlush(scheduler.IsRendering(),
                                    decision.emit_memory && !local_buffers,
                                    local_buffers, static_cast<unsigned>(image_barriers.size()));
    scheduler.EndRendering();
    scheduler.Record([memory = memory_barrier,
                      has_memory = decision.emit_memory && !local_buffers,
                      buffers = local_buffer_info,
                      buffer_count = local_buffer_count,
                      images = scheduler.RecordData(std::span<const vk::ImageMemoryBarrier2>(
                          image_barriers.data(), image_barriers.size()))](vk::CommandBuffer cmdbuf) {
        const vk::DependencyInfo info = {
            .memoryBarrierCount = has_memory ? 1U : 0U,
            .pMemoryBarriers = has_memory ? &memory : nullptr,
            .bufferMemoryBarrierCount = buffer_count,
            .pBufferMemoryBarriers = buffers.data(),
            .imageMemoryBarrierCount = static_cast<u32>(images.size()),
            .pImageMemoryBarriers = images.data(),
        };
        cmdbuf.pipelineBarrier2(info);
    });

    image_barriers.clear();
    if (decision.retire_buffer_ranges) {
        pending_mali_buffer_barriers.Clear();
        memory_barrier.srcStageMask = vk::PipelineStageFlagBits2::eNone;
        memory_barrier.srcAccessMask = vk::AccessFlagBits2::eNone;
        barrier_tracker.Clear();
        buffer_hazard_pending = false;
        ++access_epoch;
    }
}

} // namespace Vulkan
