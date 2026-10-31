// SPDX-FileCopyrightText: Copyright 2024 shadPS4 Emulator Project
// SPDX-License-Identifier: GPL-2.0-or-later

#include "common/logging/log.h"
#include "shader_recompiler/resource.h"
#include "video_core/renderer_vulkan/liverpool_to_vk.h"
#include "video_core/renderer_vulkan/vk_instance.h"
#include "video_core/texture_cache/image.h"
#include "video_core/texture_cache/image_view.h"
#include "video_core/texture_cache/robust_image_view.h"

#include <magic_enum/magic_enum.hpp>
#include <atomic>

namespace VideoCore {

vk::ImageViewType ConvertImageViewType(AmdGpu::ImageType type) {
    switch (type) {
    case AmdGpu::ImageType::Color1D:
        return vk::ImageViewType::e1D;
    case AmdGpu::ImageType::Color1DArray:
        return vk::ImageViewType::e1DArray;
    case AmdGpu::ImageType::Color2D:
    case AmdGpu::ImageType::Color2DMsaa:
        return vk::ImageViewType::e2D;
    case AmdGpu::ImageType::Color2DArray:
        return vk::ImageViewType::e2DArray;
    case AmdGpu::ImageType::Color3D:
        return vk::ImageViewType::e3D;
    default:
        UNREACHABLE();
    }
}

bool IsViewTypeCompatible(AmdGpu::ImageType view_type, AmdGpu::ImageType image_type) {
    switch (view_type) {
    case AmdGpu::ImageType::Color1D:
    case AmdGpu::ImageType::Color1DArray:
        return image_type == AmdGpu::ImageType::Color1D;
    case AmdGpu::ImageType::Color2D:
    case AmdGpu::ImageType::Color2DArray:
    case AmdGpu::ImageType::Color2DMsaa:
    case AmdGpu::ImageType::Color2DMsaaArray:
        return image_type == AmdGpu::ImageType::Color2D || image_type == AmdGpu::ImageType::Color3D;
    case AmdGpu::ImageType::Color3D:
        return image_type == AmdGpu::ImageType::Color3D;
    default:
        UNREACHABLE();
    }
}

ImageViewInfo::ImageViewInfo(const AmdGpu::Image& image, const Shader::ImageResource& desc) noexcept
    : is_storage{desc.is_written} {
    const auto dfmt = image.GetDataFmt();
    auto nfmt = image.GetNumberFmt();
    if (is_storage && nfmt == AmdGpu::NumberFormat::Srgb) {
        nfmt = AmdGpu::NumberFormat::Unorm;
    }
    format = Vulkan::LiverpoolToVK::SurfaceFormat(dfmt, nfmt);
    if (desc.is_depth) {
        format = Vulkan::LiverpoolToVK::PromoteFormatToDepth(format);
    }

    range.base.level = image.base_level;
    range.base.layer = std::min<u32>(image.base_array, image.NumLayers() - 1);
    range.extent.levels = image.NumViewLevels(desc.is_array);
    range.extent.layers = image.NumViewLayers(desc.is_array);
    type = image.GetViewType(desc.is_array);
    min_lod = static_cast<u32>(image.min_lod);

    if (!is_storage) {
        mapping = Vulkan::LiverpoolToVK::ComponentMapping(image.DstSelect());
    }
}

ImageViewInfo::ImageViewInfo(const AmdGpu::ColorBuffer& col_buffer) noexcept {
    range.base.layer = col_buffer.BaseSlice();
    range.extent.layers = col_buffer.NumSlices() - range.base.layer;
    type = range.extent.layers > 1 ? AmdGpu::ImageType::Color2DArray : AmdGpu::ImageType::Color2D;
    format =
        Vulkan::LiverpoolToVK::SurfaceFormat(col_buffer.GetDataFmt(), col_buffer.GetNumberFmt());
}

ImageViewInfo::ImageViewInfo(const AmdGpu::DepthBuffer& depth_buffer, AmdGpu::DepthView view,
                             AmdGpu::DepthControl ctl) {
    format = Vulkan::LiverpoolToVK::DepthFormat(depth_buffer.z_info.format,
                                                depth_buffer.stencil_info.format);
    is_storage = ctl.depth_write_enable;
    range.base.layer = view.slice_start;
    range.extent.layers = view.NumSlices() - range.base.layer;
    type = range.extent.layers > 1 ? AmdGpu::ImageType::Color2DArray : AmdGpu::ImageType::Color2D;
}

ImageView::ImageView(const Vulkan::Instance& instance, const ImageViewInfo& info_,
                     const Image& image)
    : info{info_} {
    vk::ImageViewUsageCreateInfo usage_ci{.usage = image.usage_flags};
    if (!info.is_storage) {
        usage_ci.usage &= ~vk::ImageUsageFlagBits::eStorage;
    }
    vk::ImageViewMinLodCreateInfoEXT min_lod_ci{};
    if (info.min_lod != 0 && instance.IsImageViewMinLodSupported()) {
        const float last_level =
            static_cast<float>(info.range.base.level + info.range.extent.levels - 1);
        min_lod_ci.minLod = std::min(static_cast<float>(info.min_lod) / 256.f, last_level);
        usage_ci.pNext = &min_lod_ci;
    }
    // When sampling D32/D16 texture from shader, the T# specifies R32/R16 format so adjust it.
    vk::Format format = info.format;
    vk::ImageAspectFlags aspect = image.aspect_mask;
    if (image.aspect_mask & vk::ImageAspectFlagBits::eDepth &&
        Vulkan::LiverpoolToVK::IsFormatDepthCompatible(format)) {
        format = image.info.pixel_format;
        aspect = vk::ImageAspectFlagBits::eDepth;
    }
    if (image.aspect_mask & vk::ImageAspectFlagBits::eStencil &&
        Vulkan::LiverpoolToVK::IsFormatStencilCompatible(format)) {
        format = image.info.pixel_format;
        aspect = vk::ImageAspectFlagBits::eStencil;
    }

    // gow3: storage writes never convert to sRGB and sRGB formats cannot be storage images
    // (AMD's driver loses the device on such a view; NVIDIA tolerates it): write through the
    // UNORM format, which stores the same bytes.
    if (info.is_storage) {
        switch (format) {
        case vk::Format::eR8G8B8A8Srgb:
            format = vk::Format::eR8G8B8A8Unorm;
            break;
        case vk::Format::eB8G8R8A8Srgb:
            format = vk::Format::eB8G8R8A8Unorm;
            break;
        case vk::Format::eA8B8G8R8SrgbPack32:
            format = vk::Format::eA8B8G8R8UnormPack32;
            break;
        case vk::Format::eR8Srgb:
            format = vk::Format::eR8Unorm;
            break;
        case vk::Format::eR8G8Srgb:
            format = vk::Format::eR8G8Unorm;
            break;
        default:
            break;
        }
    }

    // The requested view is not necessarily the physical image format. PanVK
    // accepts a smaller subset of mutable formats than Turnip. Validate the
    // actual backing and the shader-view usage before creating this view.
    // Never re-interpret compressed BCn data as RGBA or swap a R32UI view
    // for an unrelated format; this would corrupt the mip and texel layout.
    vk::Format view_format = instance.GetSupportedFormat(format, image.format_features);
    vk::ImageSubresourceRange view_range{
        .aspectMask = aspect,
        .baseMipLevel = info.range.base.level,
        .levelCount = info.range.extent.levels,
        .baseArrayLayer = info.range.base.layer,
        .layerCount = info.range.extent.layers,
    };
    const bool is_mali = instance.GetPhysicalDevice().getProperties().vendorID == 0x13B5;
    const bool shader_only = !image.usage.render_target && !image.usage.depth_target &&
                             !image.usage.vo_surface;
    if (is_mali) {
        // Attachment usage is speculative in the cache. When the view is
        // exclusively for shader access, don't require attachment/storage
        // capabilities which the shader will never use. This is important
        // for compressed BCn and packed color views on PanVK.
        // An uncompressed sampled image can be bound as a color/depth
        // attachment in a later draw, with its ImageViewInfo reused by the
        // texture cache. Narrowing its view to sampled-only would then make
        // the attachment illegal. Compressed BCn cannot be an attachment;
        // storage views have a distinct cached is_storage key.
        if (shader_only && (info.is_storage || image.info.props.is_block)) {
            const auto shader_usage = info.is_storage ? vk::ImageUsageFlagBits::eStorage
                                                      : vk::ImageUsageFlagBits::eSampled;
            usage_ci.usage &= shader_usage;
        }
        const auto backing_format = image.backing->image.image_ci.format;
        // Same physical backing for the D16S8/R8-sRGB fallback resolved by
        // Image::Image; doing so on an unrelated format is not legal.
        if (format == image.info.pixel_format && backing_format != format &&
            instance.GetSupportedFormat(format, image.format_features) == backing_format) {
            view_format = backing_format;
        }
        const auto required = info.is_storage ? vk::FormatFeatureFlagBits2::eStorageImage
                                               : vk::FormatFeatureFlagBits2::eSampledImage;
        // Color/depth attachment views can also be created via this class.
        // Keep their original handling until attachment-specific proof exists.
        const bool shader_access = shader_only || info.is_storage;
        const bool native_supported = !shader_access ||
                                      instance.IsFormatSupported(view_format, required);
        RobustImage::PhysicalView physical{
            .requested_format = view_format,
            .backing_format = backing_format,
            .view_aspects = aspect,
            .backing_aspects = image.aspect_mask,
            .components = info.mapping,
            .view_usage = usage_ci.usage,
            .backing_usage = image.usage_flags,
            .base_mip = view_range.baseMipLevel,
            .mip_count = view_range.levelCount,
            .mip_capacity = image.backing->image.image_ci.mipLevels,
            .base_layer = view_range.baseArrayLayer,
            .layer_count = view_range.layerCount,
            .layer_capacity = image.backing->image.image_ci.arrayLayers,
            .storage = info.is_storage,
            .shader_only = shader_only,
            .native_format_supported = native_supported,
        };
        auto check = RobustImage::Validate(physical);
        // Physical fallbacks may be outside Vulkan's mutable-format class,
        // but only when creation already chose the backing type from the
        // *same* original guest format. This is distinct from guest aliases.
        if (check.issue == RobustImage::Issue::IncompatiblePhysicalFormat &&
            view_format == backing_format) {
            check.issue = RobustImage::Issue::None;
        }
        if (check.issue != RobustImage::Issue::None) {
            static std::atomic<u32> warnings{0};
            if (warnings.fetch_add(1, std::memory_order_relaxed) < 32) {
                LOG_WARNING(Render_Vulkan,
                            "PanVK RobustImage::Validate issue={} request={} physical={} "
                            "usage={} image_usage={} mip={}/{} layers={}/{} guest={:#x}",
                            static_cast<u32>(check.issue), vk::to_string(view_format),
                            vk::to_string(backing_format), vk::to_string(usage_ci.usage),
                            vk::to_string(image.usage_flags), view_range.baseMipLevel,
                            view_range.levelCount, view_range.baseArrayLayer,
                            view_range.layerCount, image.info.guest_address);
            }
            if (shader_only || info.is_storage) {
                // nullDescriptor is mandatory in the Instance. This avoids
                // submitting an illegal view to the driver while the game
                // can continue rendering with a zero-valued texture.
                return;
            }
        } else {
            view_range.levelCount = check.mip_count;
            view_range.layerCount = check.layer_count;
        }
    }
    const vk::ImageViewCreateInfo image_view_ci = {
        .pNext = &usage_ci,
        .image = image.GetImage(),
        .viewType = ConvertImageViewType(info.type),
        .format = view_format,
        .components = info.mapping,
        .subresourceRange = view_range,
    };
    if (!IsViewTypeCompatible(info.type, image.info.type)) {
        LOG_ERROR(Render_Vulkan, "image view type {} is incompatible with image type {}",
                  magic_enum::enum_name(info.type), magic_enum::enum_name(image.info.type));
    }

    auto [view_result, view] = instance.GetDevice().createImageViewUnique(image_view_ci);
    ASSERT_MSG(view_result == vk::Result::eSuccess, "Failed to create image view: {}",
               vk::to_string(view_result));
    image_view = std::move(view);

    const auto view_aspect = aspect & vk::ImageAspectFlagBits::eDepth     ? "Depth"
                             : aspect & vk::ImageAspectFlagBits::eStencil ? "Stencil"
                                                                          : "Color";
    Vulkan::SetObjectName(
        instance.GetDevice(), *image_view, "ImageView {}x{}x{} {:#x}:{:#x} {}:{} {}:{} ({})",
        image.info.size.width, image.info.size.height, image.info.size.depth,
        image.info.guest_address, image.info.guest_size, info.range.base.level,
        info.range.base.level + info.range.extent.levels - 1, info.range.base.layer,
        info.range.base.layer + info.range.extent.layers - 1, view_aspect);
}

ImageView::~ImageView() = default;

} // namespace VideoCore
