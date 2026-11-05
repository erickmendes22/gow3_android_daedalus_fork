// GPL-2.0-or-later
// Mali native Vulkan image-view validation. The original Bachata release
// encodes a similar physical-view compatibility contract (format, aspect,
// component mapping, level/layer bounds and shader usage). This is an
// independent, conservative implementation; shader-level read repair and
// guest format transcoding are deliberately NOT approximated here.
#pragma once

#include <algorithm>
#include "common/types.h"
#include "video_core/renderer_vulkan/vk_common.h"
#include "video_core/texture_cache/host_compatibility.h"

namespace VideoCore::RobustImage {

enum class Issue {
    None,
    NoSubresources,
    InvalidAspect,
    IncompatiblePhysicalFormat,
    UnsupportedShaderUsage,
    InvalidStorageMapping,
};

struct PhysicalView {
    vk::Format requested_format{};
    vk::Format backing_format{};
    vk::ImageAspectFlags view_aspects{};
    vk::ImageAspectFlags backing_aspects{};
    vk::ComponentMapping components{};
    vk::ImageUsageFlags view_usage{};
    vk::ImageUsageFlags backing_usage{};
    u32 base_mip{};
    u32 mip_count{};
    u32 mip_capacity{};
    u32 base_layer{};
    u32 layer_count{};
    u32 layer_capacity{};
    bool storage{};
    bool shader_only{};
    bool native_format_supported{};
};

struct Validation {
    Issue issue = Issue::None;
    vk::Format format{};
    vk::ImageUsageFlags view_usage{};
    u32 base_mip{}, mip_count{}, base_layer{}, layer_count{};
    bool physical_remap{};
};

inline bool IsIdentity(const vk::ComponentMapping& m) {
    const auto okay = [](vk::ComponentSwizzle value, vk::ComponentSwizzle channel) {
        return value == vk::ComponentSwizzle::eIdentity || value == channel;
    };
    return okay(m.r, vk::ComponentSwizzle::eR) &&
           okay(m.g, vk::ComponentSwizzle::eG) &&
           okay(m.b, vk::ComponentSwizzle::eB) &&
           okay(m.a, vk::ComponentSwizzle::eA);
}

inline Validation Validate(const PhysicalView& v) {
    Validation out{.format = v.requested_format,
                   .view_usage = v.view_usage,
                   .base_mip = v.base_mip,
                   .mip_count = v.mip_count,
                   .base_layer = v.base_layer,
                   .layer_count = v.layer_count};
    if (!v.mip_count || !v.layer_count ||
        v.base_mip >= v.mip_capacity || v.base_layer >= v.layer_capacity) {
        out.issue = Issue::NoSubresources;
        return out;
    }
    // A malicious or malformed guest T# must not pass an out-of-bounds
    // subresource to vkCreateImageView. Clamp the count, never the base.
    out.mip_count = std::min(v.mip_count, v.mip_capacity - v.base_mip);
    out.layer_count = std::min(v.layer_count, v.layer_capacity - v.base_layer);
    const bool color_view = bool(v.view_aspects & vk::ImageAspectFlagBits::eColor);
    const bool depth_view = bool(v.view_aspects & vk::ImageAspectFlagBits::eDepth);
    const bool stencil_view = bool(v.view_aspects & vk::ImageAspectFlagBits::eStencil);
    if (!v.view_aspects ||
        (color_view && (depth_view || stencil_view)) ||
        (v.view_aspects & v.backing_aspects) != v.view_aspects) {
        out.issue = Issue::InvalidAspect;
        return out;
    }
    if (!v.view_usage ||
        (v.storage && !(v.view_usage & vk::ImageUsageFlagBits::eStorage)) ||
        (!v.storage && v.shader_only &&
         !(v.view_usage & vk::ImageUsageFlagBits::eSampled)) ||
        (v.view_usage & v.backing_usage) != v.view_usage) {
        out.issue = Issue::UnsupportedShaderUsage;
        return out;
    }
    if (v.storage && !IsIdentity(v.components)) {
        out.issue = Issue::InvalidStorageMapping;
        return out;
    }
    if (v.requested_format != v.backing_format &&
        !IsVulkanFormatCompatible(v.backing_format, v.requested_format) &&
        !IsVulkanFormatCompatible(v.requested_format, v.backing_format)) {
        // D16S8 -> D24S8/D32S8 and R8-sRGB -> R8-UNORM are selected
        // at backing-image creation. Only that exact physical backing can
        // replace its original requested format, not an unrelated R32UI,
        // R11G11B10 or BCn view.
        out.issue = Issue::IncompatiblePhysicalFormat;
        return out;
    }
    if (!v.native_format_supported) {
        // A valid physical view must never be created by pretending that
        // an unsupported format is supported. A caller may bind a null
        // descriptor for a shader-only resource (VK_EXT_robustness2).
        out.issue = Issue::UnsupportedShaderUsage;
        return out;
    }
    return out;
}

} // namespace VideoCore::RobustImage
