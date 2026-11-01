// SPDX-License-Identifier: GPL-2.0-or-later
// God of War III: bounded, opt-in PanVK render-pass COLOR + DEPTH screenshots.
// A real GPU copy is inserted immediately after the selected draw, BEFORE the
// render target is reused. Nothing here executes on Adreno or ordinary builds.
#pragma once

#include <algorithm>
#include <array>
#include <bit>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <string>
#include <vector>
#include <vulkan/vulkan.hpp>
#include <vk_mem_alloc.h>
#include "video_core/renderer_vulkan/vk_instance.h"
#include "video_core/renderer_vulkan/vk_runtime.h"
#include "video_core/renderer_vulkan/vk_scheduler.h"
#include "video_core/texture_cache/image.h"

namespace Vulkan::MaliPassCapture {

inline u16 Read16(const u8* p) {
    return u16(p[0]) | (u16(p[1]) << 8);
}
inline u32 Read32(const u8* p) {
    return u32(p[0]) | (u32(p[1]) << 8) | (u32(p[2]) << 16) | (u32(p[3]) << 24);
}
inline float ReadFloat(const u8* p) {
    return std::bit_cast<float>(Read32(p));
}
inline float HalfFloat(u16 bits) {
    const int sign = (bits >> 15) ? -1 : 1;
    const int exponent = (bits >> 10) & 0x1f;
    const int mantissa = bits & 0x3ff;
    if (exponent == 31) return 0.0f; // Invalid/NaN: visible diagnostic black.
    if (exponent == 0) return std::ldexp(float(sign * mantissa), -24);
    return std::ldexp(float(sign * (1024 + mantissa)), exponent - 25);
}
inline float Ufloat(u32 bits, int mantissa_bits) {
    const int exp = int(bits >> mantissa_bits);
    const u32 mantissa = bits & ((1u << mantissa_bits) - 1);
    if (exp == 31) return 0.f;
    if (exp == 0) return std::ldexp(float(mantissa), 1 - 15 - mantissa_bits);
    return std::ldexp(float((1u << mantissa_bits) + mantissa), exp - 15 - mantissa_bits);
}
inline u8 Byte(float v, bool hdr = false) {
    if (!std::isfinite(v)) v = 0.f;
    if (hdr) v = 1.f - std::exp(-std::max(0.f, v)); // Simple preview tonemapping.
    return u8(std::clamp(v, 0.f, 1.f) * 255.f + .5f);
}

// Snapshot format is the PHYSICAL VkImage format, not guest ImageInfo format.
// D24S8/D32S8 use DEPTH aspect only: 4 bytes per copied depth texel.
inline u32 BytesPerPixel(vk::Format format, bool depth) {
    if (depth) {
        switch (format) {
        case vk::Format::eD16Unorm: return 2;
        case vk::Format::eD32Sfloat:
        case vk::Format::eD24UnormS8Uint:
        case vk::Format::eD32SfloatS8Uint: return 4;
        default: return 0;
        }
    }
    switch (format) {
    case vk::Format::eR8G8B8A8Unorm:
    case vk::Format::eR8G8B8A8Srgb:
    case vk::Format::eB8G8R8A8Unorm:
    case vk::Format::eB8G8R8A8Srgb:
    case vk::Format::eA2R10G10B10UnormPack32:
    case vk::Format::eA2B10G10R10UnormPack32:
    case vk::Format::eB10G11R11UfloatPack32: return 4;
    case vk::Format::eR16G16B16A16Sfloat: return 8;
    case vk::Format::eR32G32B32A32Sfloat: return 16;
    default: return 0;
    }
}
inline void Pixel(const u8* input, vk::Format format, bool depth, u8* rgb) {
    if (depth) {
        float d = 0.f;
        switch (format) {
        case vk::Format::eD16Unorm: d = float(Read16(input)) / 65535.f; break;
        case vk::Format::eD24UnormS8Uint: d = float(Read32(input) & 0xffffff) / 16777215.f; break;
        case vk::Format::eD32Sfloat:
        case vk::Format::eD32SfloatS8Uint: d = ReadFloat(input); break;
        default: break;
        }
        rgb[0] = rgb[1] = rgb[2] = Byte(d);
        return;
    }
    switch (format) {
    case vk::Format::eR8G8B8A8Srgb:
    case vk::Format::eR8G8B8A8Unorm:
        rgb[0] = input[0]; rgb[1] = input[1]; rgb[2] = input[2]; break;
    case vk::Format::eB8G8R8A8Srgb:
    case vk::Format::eB8G8R8A8Unorm:
        rgb[0] = input[2]; rgb[1] = input[1]; rgb[2] = input[0]; break;
    case vk::Format::eA2R10G10B10UnormPack32: {
        const u32 v = Read32(input);
        rgb[0] = u8(((v >> 20) & 1023) * 255 / 1023);
        rgb[1] = u8(((v >> 10) & 1023) * 255 / 1023);
        rgb[2] = u8((v & 1023) * 255 / 1023);
        break;
    }
    case vk::Format::eA2B10G10R10UnormPack32: {
        const u32 v = Read32(input);
        rgb[0] = u8((v & 1023) * 255 / 1023);
        rgb[1] = u8(((v >> 10) & 1023) * 255 / 1023);
        rgb[2] = u8(((v >> 20) & 1023) * 255 / 1023);
        break;
    }
    case vk::Format::eB10G11R11UfloatPack32: {
        const u32 v = Read32(input);
        rgb[0] = Byte(Ufloat(v & 0x7ff, 6), true);
        rgb[1] = Byte(Ufloat((v >> 11) & 0x7ff, 6), true);
        rgb[2] = Byte(Ufloat(v >> 22, 5), true);
        break;
    }
    case vk::Format::eR16G16B16A16Sfloat:
        for (int c = 0; c < 3; ++c) rgb[c] = Byte(HalfFloat(Read16(input + c * 2)), true);
        break;
    case vk::Format::eR32G32B32A32Sfloat:
        for (int c = 0; c < 3; ++c) rgb[c] = Byte(ReadFloat(input + c * 4), true);
        break;
    default: rgb[0] = rgb[1] = rgb[2] = 0; break;
    }
}

// A plain 24-bit BMP allows viewing pixels on-device without external tools.
// Scales in software AFTER the fence; never writes into game images.
inline bool SaveBmp(const std::string& path, const u8* pixels, u32 w, u32 h, u32 bytes_per_pixel,
                    vk::Format format, bool depth, u64& nonblack) {
    constexpr u32 preview_w = 960, preview_h = 540;
    const u32 dw = std::min(w, preview_w), dh = std::min(h, preview_h);
    const u32 stride = (dw * 3 + 3) & ~u32{3};
    const u32 data_size = stride * dh;
    std::array<u8, 54> header{};
    header[0] = 'B'; header[1] = 'M';
    const auto set16 = [&](size_t o, u32 v) {
        header[o] = u8(v); header[o + 1] = u8(v >> 8);
    };
    const auto set32 = [&](size_t o, u32 v) {
        for (int i = 0; i < 4; ++i) header[o + i] = u8(v >> (8 * i));
    };
    set32(2, 54 + data_size); set32(10, 54); set32(14, 40);
    set32(18, dw); set32(22, dh); set16(26, 1); set16(28, 24); set32(34, data_size);
    FILE* file = std::fopen(path.c_str(), "wb");
    if (!file) return false;
    bool ok = std::fwrite(header.data(), 1, header.size(), file) == header.size();
    std::vector<u8> row(stride);
    nonblack = 0;
    for (u32 y = 0; ok && y < dh; ++y) {
        std::fill(row.begin(), row.end(), u8{0});
        const u32 sy = u32((u64(dh - 1 - y) * h) / dh);
        for (u32 x = 0; x < dw; ++x) {
            const u32 sx = u32((u64(x) * w) / dw);
            const u8* pixel = pixels + (size_t(sy) * w + sx) * bytes_per_pixel;
            u8 rgb[3]{};
            Pixel(pixel, format, depth, rgb);
            nonblack += (rgb[0] | rgb[1] | rgb[2]) != 0;
            u8* dst = row.data() + size_t(x) * 3;
            dst[0] = rgb[2]; dst[1] = rgb[1]; dst[2] = rgb[0];
        }
        ok = std::fwrite(row.data(), 1, row.size(), file) == row.size();
    }
    if (std::fclose(file) != 0) ok = false;
    return ok;
}

// Called only for a handful of 3D draws when GOW3_MALI_AUTOCAPTURE=1 on Arm.
// Returns reason for any skipped target to the per-pass metadata file.
inline std::string Queue(const Instance& instance, Scheduler& scheduler, Runtime& runtime,
                         VideoCore::Image& image, bool depth, const std::string& path) {
    const auto& ci = image.backing->image.image_ci;
    const u32 w = ci.extent.width, h = ci.extent.height;
    const u32 bpp = BytesPerPixel(ci.format, depth);
    if (!bpp) return "unsupported_physical_format";
    if (!w || !h || w > 4096 || h > 4096) return "invalid_extent";
    if (ci.imageType != vk::ImageType::e2D || ci.samples != vk::SampleCountFlagBits::e1)
        return "not_single_sample_2d";
    if (ci.mipLevels != 1 || ci.arrayLayers != 1) return "non_base_subresource";
    if (!(ci.usage & vk::ImageUsageFlagBits::eTransferSrc)) return "transfer_source_not_supported";
    const VkDeviceSize bytes = VkDeviceSize(w) * h * bpp;
    if (bytes > (32ull << 20)) return "snapshot_exceeds_32MiB";
    const VkBufferCreateInfo buffer_info{
        .sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,
        .size = bytes,
        .usage = VK_BUFFER_USAGE_TRANSFER_DST_BIT,
    };
    const VmaAllocationCreateInfo allocation_info{
        .flags = VMA_ALLOCATION_CREATE_MAPPED_BIT | VMA_ALLOCATION_CREATE_HOST_ACCESS_RANDOM_BIT,
        .usage = VMA_MEMORY_USAGE_AUTO_PREFER_HOST,
    };
    VkBuffer buffer{};
    VmaAllocation allocation{};
    VmaAllocationInfo mapped{};
    const VkResult created = vmaCreateBuffer(instance.GetAllocator(), &buffer_info,
                                             &allocation_info, &buffer, &allocation, &mapped);
    if (created != VK_SUCCESS || !mapped.pMappedData) {
        if (created == VK_SUCCESS) vmaDestroyBuffer(instance.GetAllocator(), buffer, allocation);
        return "staging_allocation_failed";
    }

    // IMPORTANT: end the guest render pass, then use tracked transitions. The next
    // guest draw restores the color/depth attachment layout through Runtime::Transit.
    scheduler.EndRendering();
    runtime.Transit(&image, vk::ImageLayout::eTransferSrcOptimal,
                    vk::PipelineStageFlagBits2::eTransfer, vk::AccessFlagBits2::eTransferRead);
    runtime.FlushBarriers();
    const vk::BufferImageCopy copy{
        .bufferOffset = 0,
        .imageSubresource = {.aspectMask = depth ? vk::ImageAspectFlagBits::eDepth
                                                 : vk::ImageAspectFlagBits::eColor,
                             .mipLevel = 0, .baseArrayLayer = 0, .layerCount = 1},
        .imageExtent = {w, h, 1},
    };
    scheduler.Record([img = image.GetImage(), dst = vk::Buffer{buffer}, copy](vk::CommandBuffer cb) {
        cb.copyImageToBuffer(img, vk::ImageLayout::eTransferSrcOptimal, dst, copy);
    });
    scheduler.DeferPriorityOperation([allocator = instance.GetAllocator(), buffer, allocation,
                                      mapped, bytes, bpp, format = ci.format, w, h, path, depth] {
        const VkResult invalidate = vmaInvalidateAllocation(allocator, allocation, 0, bytes);
        u64 nonblack = 0;
        const bool ok = invalidate == VK_SUCCESS &&
                        SaveBmp(path, static_cast<const u8*>(mapped.pMappedData), w, h,
                                bpp, format, depth, nonblack);
        std::printf("GOW3_MALI_PASS_IMAGE path=%s size=%ux%u depth=%d format=%s "
                    "nonblack=%llu/%llu ok=%d\n",
                    path.c_str(), w, h, int(depth), vk::to_string(format).c_str(),
                    static_cast<unsigned long long>(nonblack),
                    static_cast<unsigned long long>(u64(std::min(w, 960u)) * std::min(h, 540u)),
                    int(ok));
        vmaDestroyBuffer(allocator, buffer, allocation);
    });
    return "queued";
}

inline bool Enabled(const Instance& instance) {
    static const bool requested = [] {
        const char* value = std::getenv("GOW3_MALI_AUTOCAPTURE");
        return value && value[0] == '1';
    }();
    return requested && instance.GetPhysicalDevice().getProperties().vendorID == 0x13B5;
}

inline void CaptureDraw(const Instance& instance, Scheduler& scheduler, Runtime& runtime,
                        const std::array<VideoCore::Image*, 3>& colors,
                        VideoCore::Image* depth, bool depth_enabled, bool depth_write,
                        u32 mrt_mask, u32 sample_count, u64 vs_hash, u64 ps_hash,
                        u32 area_width, u32 area_height) {
    const VideoCore::Image* first = colors[0];
    if (!first || !first->backing || first->info.size.width < 320 ||
        first->info.size.height < 180) return;
    const bool has_depth = depth_enabled && depth && depth->backing;
    static u32 depth_draws = 0;
    static bool first_color_only = false;
    u32 number = 0;
    bool take = false;
    if (has_depth) {
        number = ++depth_draws;
        take = number == 1 || number == 8 || number == 32 ||
               number == 128 || number == 512;
    } else if (!first_color_only) {
        first_color_only = true;
        take = true;
    }
    if (!take) return;
    const char* directory = std::getenv("GOW3_MALI_CAPTURE_DIR");
    if (!directory || !*directory) {
        std::printf("GOW3_MALI_PASS_CAPTURE no_capture_dir\n");
        return;
    }
    char base[512];
    std::snprintf(base, sizeof(base), "%s/scene_%04u_%s", directory, number,
                  has_depth ? "3d" : "color");
    const std::string prefix{base};
    const std::string meta_path = prefix + "_pass.txt";
    FILE* meta = std::fopen(meta_path.c_str(), "w");
    if (meta) {
        std::fprintf(meta, "scene_3d=%d pass_draw=%u vs=%016llx ps=%016llx "
                           "mrt_mask=%08x depth_enabled=%d depth_write=%d "
                           "render_area=%ux%u samples=%u\n",
                     int(has_depth), number,
                     static_cast<unsigned long long>(vs_hash),
                     static_cast<unsigned long long>(ps_hash), mrt_mask,
                     int(depth_enabled), int(depth_write), area_width, area_height,
                     sample_count);
        std::fprintf(meta, "GPU snapshot was recorded after the selected draw, before target reuse.\n");
        std::fprintf(meta, "HDR color previews are tonemapped; depth is a normalized grayscale.\n");
    }
    std::printf("GOW3_MALI_PASS_CAPTURE draw=%u depth=%d vs=%016llx ps=%016llx "
                "colors=%u area=%ux%u\n", number, int(has_depth),
                static_cast<unsigned long long>(vs_hash),
                static_cast<unsigned long long>(ps_hash),
                unsigned(colors[0] != nullptr) + unsigned(colors[1] != nullptr) +
                unsigned(colors[2] != nullptr), area_width, area_height);
    for (u32 cb = 0; cb < colors.size(); ++cb) {
        auto* target = colors[cb];
        if (!target || !target->backing) continue;
        char name[32];
        std::snprintf(name, sizeof(name), "_color%u.bmp", cb);
        const std::string path = prefix + name;
        const vk::Format format = target->backing->image.image_ci.format;
        const std::string status = !target->binding.is_bound
              ? Queue(instance, scheduler, runtime, *target, false, path)
              : "texture_feedback_alias";
        if (meta) std::fprintf(meta,
            "color%u guest=%#llx format=%s %ux%u result=%s file=%s\n",
            cb, static_cast<unsigned long long>(target->info.guest_address),
            vk::to_string(format).c_str(), target->info.size.width,
            target->info.size.height, status.c_str(), path.c_str());
        std::printf("GOW3_MALI_PASS_CAPTURE color=%u guest=%#llx format=%s result=%s\n",
                    cb, static_cast<unsigned long long>(target->info.guest_address),
                    vk::to_string(format).c_str(), status.c_str());
    }
    if (has_depth) {
        const std::string path = prefix + "_depth.bmp";
        const vk::Format format = depth->backing->image.image_ci.format;
        const std::string status = !depth->binding.is_bound
              ? Queue(instance, scheduler, runtime, *depth, true, path)
              : "texture_feedback_alias";
        if (meta) std::fprintf(meta,
            "depth guest=%#llx format=%s %ux%u result=%s file=%s\n",
            static_cast<unsigned long long>(depth->info.guest_address),
            vk::to_string(format).c_str(), depth->info.size.width,
            depth->info.size.height, status.c_str(), path.c_str());
        std::printf("GOW3_MALI_PASS_CAPTURE depth guest=%#llx format=%s result=%s\n",
                    static_cast<unsigned long long>(depth->info.guest_address),
                    vk::to_string(format).c_str(), status.c_str());
    } else if (meta) {
        std::fprintf(meta, "depth not_active_on_this_pass\n");
    }
    if (meta) std::fclose(meta);
}

} // namespace Vulkan::MaliPassCapture
