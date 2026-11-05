// SPDX-FileCopyrightText: Copyright 2024 shadPS4 Emulator Project
// SPDX-License-Identifier: GPL-2.0-or-later

#include "gow3_toggles.h"
#include <ranges>
#include "common/assert.h"
#include "video_core/renderer_vulkan/liverpool_to_vk.h"
#include "video_core/renderer_vulkan/vk_instance.h"
#include "video_core/renderer_vulkan/vk_runtime.h"
#include "video_core/renderer_vulkan/vk_mali_visual_trace.h"
#include "video_core/renderer_vulkan/vk_mali_perf_stats.h"
#include "video_core/renderer_vulkan/vk_scheduler.h"
#include "video_core/texture_cache/blit_helper.h"
#include "video_core/texture_cache/image.h"
#include "video_core/texture_cache/read_barrier_policy.h"

#include <vk_mem_alloc.h>
#include <algorithm>
#include <array>
#include <mutex>
#include <vector>
#include <cstdlib>

namespace VideoCore {

using namespace Vulkan;

Common::IncrementalIdProvider<u64> Image::global_image_uid{};

static vk::ImageUsageFlags ImageUsageFlags(const Vulkan::Instance& instance,
                                           const ImageInfo& info) {
    vk::ImageUsageFlags usage = vk::ImageUsageFlagBits::eTransferSrc |
                                vk::ImageUsageFlagBits::eTransferDst |
                                vk::ImageUsageFlagBits::eSampled;
    if (!info.props.is_block) {
        if (info.props.is_depth) {
            usage |= vk::ImageUsageFlagBits::eDepthStencilAttachment;
        } else {
            usage |= vk::ImageUsageFlagBits::eColorAttachment;
            if (instance.IsAttachmentFeedbackLoopLayoutSupported()) {
                usage |= vk::ImageUsageFlagBits::eAttachmentFeedbackLoopEXT;
            }
            // Always create images with storage flag to avoid needing re-creation in case of e.g
            // compute clears. This sacrifices a bit of performance but is less work. ExtendedUsage
            // flag is also used. The exception is multisample images when storage is not supported
            // (shaderStorageImageMultisample): with ExtendedUsage a driver that cannot store to a
            // multisample image may return only one supported sample, losing the MSAA render.
            if (info.num_samples == 1 || instance.IsMultisampleStorageImageSupported())
                usage |= vk::ImageUsageFlagBits::eStorage;
        }
    } else {
        // Similarly to above, we specify storage usage. This is typically not supported by
        // compressed formats, but may be used for uncompressed views. In order to satisfy this,
        // we will also specify the extended usage bit.
        usage |= vk::ImageUsageFlagBits::eStorage;
    }

    return usage;
}

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
        UNREACHABLE();
    }
}

static vk::FormatFeatureFlags2 FormatFeatureFlags(const vk::ImageUsageFlags usage_flags) {
    vk::FormatFeatureFlags2 feature_flags{};
    if (usage_flags & vk::ImageUsageFlagBits::eTransferSrc) {
        feature_flags |= vk::FormatFeatureFlagBits2::eTransferSrc;
    }
    if (usage_flags & vk::ImageUsageFlagBits::eTransferDst) {
        feature_flags |= vk::FormatFeatureFlagBits2::eTransferDst;
    }
    if (usage_flags & vk::ImageUsageFlagBits::eSampled) {
        feature_flags |= vk::FormatFeatureFlagBits2::eSampledImage;
    }
    if (usage_flags & vk::ImageUsageFlagBits::eColorAttachment) {
        feature_flags |= vk::FormatFeatureFlagBits2::eColorAttachment;
    }
    if (usage_flags & vk::ImageUsageFlagBits::eDepthStencilAttachment) {
        feature_flags |= vk::FormatFeatureFlagBits2::eDepthStencilAttachment;
    }
    // Note: StorageImage is intentionally ignored for now since it is always set, and can mess up
    // compatibility checks.
    return feature_flags;
}

// Two separate GPU-image pools, NEVER a BC3<->RGBA32 format alias. Every reuse
// requires the identical VkImageCreateInfo and the same VMA allocator.
// Scheduler::DeferOperation destroys retired Image objects only after the
// Vulkan submission has completed, so returned images cannot be in flight.
// Reusing the VkImage saves PanVK BC emulation shadow/image setup and VMA work.
namespace {
struct RetiredBcImage {
    VkImage image{};
    VmaAllocation allocation{};
    VmaAllocator allocator{};
    VkImageCreateInfo create{};
    VkDeviceSize bytes{};
};
struct BcPool {
    std::mutex mutex;
    std::vector<RetiredBcImage> images;
    VkDeviceSize bytes = 0;
    uint64_t hits = 0, misses = 0, stored = 0, discarded = 0;
};
BcPool& GetBcPool() {
    // Deliberately never destroyed by static teardown. Instance::~Instance()
    // calls FlushMaliBcImagePool before its VMA allocator is destroyed.
    static auto* const pool = new BcPool{};
    return *pool;
}
BcPool& GetRgba128Pool() {
    static auto* const pool = new BcPool{};
    return *pool;
}
constexpr VkDeviceSize BcPoolLimit = 128ULL * 1024 * 1024;
constexpr VkDeviceSize BcPoolEntryLimit = 64ULL * 1024 * 1024;
constexpr size_t BcPoolMaxEntries = 24;
// The 200 R32G32B32A32Uint creations/641 ms on G720 justify recycling
// identically described, GPU-retired images. Separate quota means no BCn
// eviction regression; 64 MiB maximum guards against OOM on unified memory.
constexpr VkDeviceSize Rgba128PoolLimit = 64ULL * 1024 * 1024;
constexpr VkDeviceSize Rgba128PoolEntryLimit = 32ULL * 1024 * 1024;
constexpr size_t Rgba128PoolMaxEntries = 24;
bool IsRgba128Image(const VkImageCreateInfo& ci) {
    return ci.format == VK_FORMAT_R32G32B32A32_UINT;
}
BcPool& ImagePoolFor(const VkImageCreateInfo& ci) {
    return IsRgba128Image(ci) ? GetRgba128Pool() : GetBcPool();
}
VkDeviceSize PoolLimit(const VkImageCreateInfo& ci) {
    return IsRgba128Image(ci) ? Rgba128PoolLimit : BcPoolLimit;
}
size_t PoolMaxEntries(const VkImageCreateInfo& ci) {
    return IsRgba128Image(ci) ? Rgba128PoolMaxEntries : BcPoolMaxEntries;
}
void ReportImagePool(const BcPool& pool, bool rgba128) {
    std::printf("GOW3_%s_IMAGE_POOL hits=%llu misses=%llu stored=%llu drop=%llu retained_mib=%llu\n",
                rgba128 ? "RGBA128" : "BC",
                (unsigned long long)pool.hits, (unsigned long long)pool.misses,
                (unsigned long long)pool.stored, (unsigned long long)pool.discarded,
                (unsigned long long)(pool.bytes >> 20));
}

bool SameBcCreate(const VkImageCreateInfo& a, const VkImageCreateInfo& b) {
    return !a.pNext && !b.pNext &&
        a.flags == b.flags && a.imageType == b.imageType &&
        a.format == b.format && a.extent.width == b.extent.width &&
        a.extent.height == b.extent.height && a.extent.depth == b.extent.depth &&
        a.mipLevels == b.mipLevels && a.arrayLayers == b.arrayLayers &&
        a.samples == b.samples && a.tiling == b.tiling && a.usage == b.usage &&
        a.sharingMode == b.sharingMode && a.queueFamilyIndexCount == 0 &&
        b.queueFamilyIndexCount == 0 && a.initialLayout == b.initialLayout;
}

bool BcPoolHasBudget(VmaAllocator allocator) {
    // Do not hold a recyclable pool when the shared RAM heap is near exhaustion.
    const VkPhysicalDeviceMemoryProperties* props{};
    vmaGetMemoryProperties(allocator, &props);
    if (!props) return false;
    std::array<VmaBudget, VK_MAX_MEMORY_HEAPS> budgets{};
    vmaGetHeapBudgets(allocator, budgets.data());
    bool found_local = false;
    for (uint32_t i = 0; i < props->memoryHeapCount; ++i) {
        if (!(props->memoryHeaps[i].flags & VK_MEMORY_HEAP_DEVICE_LOCAL_BIT)) continue;
        if (!budgets[i].budget) continue;
        found_local = true;
        // When free headroom is <10% of the live budget, destroy freed
        // images rather than allowing this pool to retain additional RAM.
        if (budgets[i].usage * 10 > budgets[i].budget * 9) return false;
    }
    return found_local;
}
void DestroyBcEntry(RetiredBcImage& e) {
    if (e.image) vmaDestroyImage(e.allocator, e.image, e.allocation);
    e.image = VK_NULL_HANDLE;
}
void TrimBcPool(BcPool& pool, VkDeviceSize need, const VkImageCreateInfo& ci) {
    while (!pool.images.empty() &&
           (pool.bytes + need > PoolLimit(ci) || pool.images.size() >= PoolMaxEntries(ci))) {
        auto e = pool.images.front();
        pool.images.erase(pool.images.begin());
        pool.bytes -= e.bytes;
        ++pool.discarded;
        DestroyBcEntry(e);
    }
}
bool TakeBcImage(VmaAllocator allocator, const vk::ImageCreateInfo& ci,
                 VkImage& image, VmaAllocation& allocation, VkDeviceSize& bytes) {
    const auto raw = static_cast<VkImageCreateInfo>(ci);
    auto& pool = ImagePoolFor(raw);
    std::lock_guard lock{pool.mutex};
    const auto it = std::find_if(pool.images.rbegin(), pool.images.rend(),
        [&](const RetiredBcImage& e) {
            return e.allocator == allocator && SameBcCreate(e.create, raw);
        });
    if (it == pool.images.rend()) {
        ++pool.misses;
        if ((pool.misses + pool.hits) % (IsRgba128Image(raw) ? 64 : 128) == 0)
            ReportImagePool(pool, IsRgba128Image(raw));
        return false;
    }
    auto e = *it;
    pool.images.erase(std::next(it).base());
    pool.bytes -= e.bytes;
    image = e.image;
    allocation = e.allocation;
    bytes = e.bytes;
    ++pool.hits;
    if ((pool.misses + pool.hits) % (IsRgba128Image(raw) ? 64 : 128) == 0)
        ReportImagePool(pool, IsRgba128Image(raw));
    return true;
}
bool ReturnBcImage(VmaAllocator allocator, const vk::ImageCreateInfo& ci,
                   VkImage image, VmaAllocation allocation, VkDeviceSize bytes) {
    auto raw = static_cast<VkImageCreateInfo>(ci);
    const auto max_entry = IsRgba128Image(raw) ? Rgba128PoolEntryLimit : BcPoolEntryLimit;
    if (!bytes || bytes > max_entry) return false;
    if (raw.pNext || raw.queueFamilyIndexCount) return false;
    auto& pool = ImagePoolFor(raw);
    std::lock_guard lock{pool.mutex};
    if (!BcPoolHasBudget(allocator)) {
        // Image cache memory must never compete with live textures at high
        // pressure; release all previously pooled entries on this allocator.
        for (size_t i = pool.images.size(); i-- > 0;) {
            if (pool.images[i].allocator != allocator) continue;
            auto e = pool.images[i];
            pool.images.erase(pool.images.begin() + i);
            pool.bytes -= e.bytes;
            ++pool.discarded;
            DestroyBcEntry(e);
        }
        return false;
    }
    TrimBcPool(pool, bytes, raw);
    if (pool.bytes + bytes > PoolLimit(raw)) return false;
    raw.pNext = nullptr;
    raw.pQueueFamilyIndices = nullptr;
    pool.images.push_back({image, allocation, allocator, raw, bytes});
    pool.bytes += bytes;
    ++pool.stored;
    return true;
}
} // namespace

void FlushMaliBcImagePool(VmaAllocator allocator) {
    // Both pools are retired before VMA allocator teardown; each pool owns
    // completely independent image handles, quotas and hit/miss counters.
    for (auto* target : {&GetBcPool(), &GetRgba128Pool()}) {
        auto& pool = *target;
        std::lock_guard lock{pool.mutex};
        for (size_t i = pool.images.size(); i-- > 0;) {
            if (pool.images[i].allocator != allocator) continue;
            auto e = pool.images[i];
            pool.images.erase(pool.images.begin() + i);
            pool.bytes -= e.bytes;
            DestroyBcEntry(e);
        }
    }
    auto& pool = GetBcPool();
    std::printf("GOW3_BC_IMAGE_POOL final_hits=%llu misses=%llu stored=%llu drop=%llu\n",
        (unsigned long long)pool.hits, (unsigned long long)pool.misses,
        (unsigned long long)pool.stored, (unsigned long long)pool.discarded);
}

UniqueImage::~UniqueImage() {
    Destroy();
}

void UniqueImage::Destroy() {
    if (image) {
        const VkImage raw = static_cast<VkImage>(image);
        if (!recycle_bc || !ReturnBcImage(allocator, image_ci, raw, allocation, size_bytes))
            vmaDestroyImage(allocator, raw, allocation);
        image = vk::Image{};
        allocation = VK_NULL_HANDLE;
        size_bytes = 0;
        recycle_bc = false;
        reused_from_pool = false;
    }
}

void UniqueImage::Create(const vk::ImageCreateInfo& image_ci) {
    this->image_ci = image_ci;
    ASSERT(!image);
    const VmaAllocationCreateInfo alloc_ci = {
        .flags = VMA_ALLOCATION_CREATE_WITHIN_BUDGET_BIT,
        .usage = VMA_MEMORY_USAGE_AUTO_PREFER_DEVICE,
        .requiredFlags = 0,
        .preferredFlags = 0,
        .pool = VK_NULL_HANDLE,
        .pUserData = nullptr,
    };

    const VkImageCreateInfo image_ci_unsafe = static_cast<VkImageCreateInfo>(image_ci);
    VkImage unsafe_image{};
    if (recycle_bc && TakeBcImage(allocator, image_ci, unsafe_image, allocation, size_bytes)) {
        image = vk::Image{unsafe_image};
        reused_from_pool = true;
        return;
    }
    reused_from_pool = false;
    VmaAllocationInfo alloc_info{};
    VkResult result = vmaCreateImage(allocator, &image_ci_unsafe, &alloc_ci, &unsafe_image,
                                     &allocation, &alloc_info);
    ASSERT_MSG(result == VK_SUCCESS, "Failed allocating image with error {}",
               vk::to_string(vk::Result{result}));
    image = vk::Image{unsafe_image};
    size_bytes = alloc_info.size;
}

Image::Image(const Vulkan::Instance& instance, Vulkan::Runtime& runtime_,
             Common::SlotVector<ImageView>& slot_image_views_, const ImageInfo& info_)
    : guest_begin{info_.guest_address}, guest_end{info_.guest_address + info_.guest_size},
      info{info_}, runtime{&runtime_}, slot_image_views{&slot_image_views_} {
    Gow3Stats::Timer timer{Gow3Stats::t_image_create};
    // Per-image immutable flag: the RAR barrier policy never changes while a
    // Vulkan image is live. This is scoped to PanVK; =0 reproduces old behavior.
    const char* rar_toggle = std::getenv("GOW3_MALI_IMAGE_RAR_ELIDE");
    mali_read_only_elision = std::getenv("GOW3_ANDROID_PORT") &&
        instance.GetPhysicalDevice().getProperties().vendorID == 0x13B5 &&
        (!rar_toggle || rar_toggle[0] != '0');
    if (info.pixel_format == vk::Format::eUndefined) {
        return;
    }

    const Vulkan::MaliPerfStats::Scoped mali_image_build{
        info.props.is_block ? Vulkan::MaliPerfStats::Stage::NewBcImage
        : info.pixel_format == vk::Format::eR32G32B32A32Uint
              ? Vulkan::MaliPerfStats::Stage::NewRgba128Image
              : Vulkan::MaliPerfStats::Stage::NewOtherImage,
        Vulkan::MaliPerfStats::Enabled()};
    image_uid = global_image_uid.Next();
    mip_hashes.resize(info.resources.levels);
    vk::ImageCreateFlags flags{vk::ImageCreateFlagBits::eMutableFormat |
                               vk::ImageCreateFlagBits::eExtendedUsage};
    if (info.props.is_volume) {
        flags |= vk::ImageCreateFlagBits::e2DArrayCompatible;
        if (instance.Is2dViewOf3dSupported()) {
            flags |= vk::ImageCreateFlagBits::e2DViewCompatibleEXT;
        }
    }
    if (info.props.is_block && instance.IsBlockTexelViewSupported()) {
        flags |= vk::ImageCreateFlagBits::eBlockTexelViewCompatible;
    }

    usage_flags = ImageUsageFlags(instance, info);
    format_features = FormatFeatureFlags(usage_flags);
    if (info.props.is_depth) {
        aspect_mask = vk::ImageAspectFlagBits::eDepth;
        if (info.props.has_stencil) {
            aspect_mask |= vk::ImageAspectFlagBits::eStencil;
        }
    }

    constexpr auto tiling = vk::ImageTiling::eOptimal;
    const auto supported_format = instance.GetSupportedFormat(info.pixel_format, format_features);
    vk::PhysicalDeviceImageFormatInfo2 format_info{
        .format = supported_format,
        .type = ConvertImageType(info.type),
        .tiling = tiling,
        .usage = usage_flags,
        .flags = flags,
    };
    auto image_format_properties =
        instance.GetPhysicalDevice().getImageFormatProperties2(format_info);
    // gow3: storage usage is speculative (see ImageUsageFlags). Drivers that refuse it for a
    // format (AMD's Windows driver for BC6H) get the image without it: creating the unsupported
    // combination anyway loses the device a few frames later.
    if (image_format_properties.result == vk::Result::eErrorFormatNotSupported &&
        (usage_flags & vk::ImageUsageFlagBits::eStorage)) {
        format_info.usage = usage_flags & ~vk::ImageUsageFlagBits::eStorage;
        image_format_properties = instance.GetPhysicalDevice().getImageFormatProperties2(format_info);
        if (image_format_properties.result == vk::Result::eSuccess) {
            usage_flags = format_info.usage;
            format_features = FormatFeatureFlags(usage_flags);
        } else {
            format_info.usage = usage_flags;
        }
    }
    // The PanVK BCn decoder can sample compressed blocks even when optional
    // ExtendedUsage is unavailable for the combination of image flags and
    // transfer usage. Keep BC data compressed and let the driver decode it:
    // silently reinterpreting BCn as RGBA8 would corrupt pitches and mipmaps.
    // Scope this retry strictly to Arm; Adreno retains the prior flags.
    if (image_format_properties.result == vk::Result::eErrorFormatNotSupported &&
        info.props.is_block &&
        instance.GetPhysicalDevice().getProperties().vendorID == 0x13B5 &&
        (format_info.flags & vk::ImageCreateFlagBits::eExtendedUsage)) {
        const auto original_flags = format_info.flags;
        format_info.flags &= ~vk::ImageCreateFlagBits::eExtendedUsage;
        const auto retry = instance.GetPhysicalDevice().getImageFormatProperties2(format_info);
        if (retry.result == vk::Result::eSuccess) {
            flags = format_info.flags;
            image_format_properties = retry;
            LOG_WARNING(Render_Vulkan,
                        "PanVK BCn image compatibility: format {} accepted without "
                        "optional ExtendedUsage (usage {}, flags {})",
                        vk::to_string(supported_format), vk::to_string(usage_flags),
                        vk::to_string(flags));
        } else {
            format_info.flags = original_flags;
        }
    }
    if (image_format_properties.result == vk::Result::eErrorFormatNotSupported) {
        if (Vulkan::MaliVisualTrace::Enabled(instance.GetPhysicalDevice().getProperties().vendorID)) {
            const auto n = Vulkan::MaliVisualTrace::Add(Vulkan::MaliVisualTrace::Counts::unsupported_images);
            if (Vulkan::MaliVisualTrace::Sample(n))
                std::printf("GOW3_MALI_VISUAL event=image_unsupported seq=%llu uid=%llu guest=%#llx guest_format=%s physical=%s usage=%s\n",
                            (unsigned long long)n, (unsigned long long)image_uid,
                            (unsigned long long)info.guest_address,
                            vk::to_string(info.pixel_format).c_str(),
                            vk::to_string(supported_format).c_str(),
                            vk::to_string(format_info.usage).c_str());
        }
        LOG_ERROR(Render_Vulkan, "image format {} type {} is not supported (flags {}, usage {})",
                  vk::to_string(supported_format), vk::to_string(format_info.type),
                  vk::to_string(format_info.flags), vk::to_string(format_info.usage));
    }
    supported_samples = image_format_properties.result == vk::Result::eSuccess
                            ? image_format_properties.value.imageFormatProperties.sampleCounts
                            : vk::SampleCountFlagBits::e1;

    const vk::ImageCreateInfo image_ci = {
        .flags = flags,
        .imageType = ConvertImageType(info.type),
        .format = supported_format,
        .extent{
            .width = info.size.width,
            .height = info.size.height,
            .depth = info.size.depth,
        },
        .mipLevels = static_cast<u32>(info.resources.levels),
        .arrayLayers = static_cast<u32>(info.resources.layers),
        .samples = LiverpoolToVK::NumSamples(info.num_samples, supported_samples),
        .tiling = tiling,
        .usage = usage_flags,
        .initialLayout = vk::ImageLayout::eUndefined,
    };

    backing = &backing_images.emplace_back();
    backing->num_samples = info.num_samples;
    backing->image = UniqueImage{instance.GetDevice(), instance.GetAllocator()};
    // Recycle ONLY completed images with an identical VkImageCreateInfo.
    // Two independent bounded pools: compressed BCn and the R32G32B32A32Uint
    // image used by the PS4 guest's opposite-format layout. Not cross-format
    // aliases: the existing guard and GPU-modified data rules stay unchanged.
    static const bool bc_pool_enabled = [] {
        const char* option = std::getenv("GOW3_MALI_BC_IMAGE_POOL");
        return !option || option[0] != '0';
    }();
    static const bool rgba128_pool_enabled = [] {
        const char* option = std::getenv("GOW3_MALI_RGBA128_IMAGE_POOL");
        return !option || option[0] != '0';
    }();
    const bool is_mali = instance.GetPhysicalDevice().getProperties().vendorID == 0x13B5 &&
                         std::getenv("GOW3_ANDROID_PORT") != nullptr;
    backing->image.recycle_bc = is_mali &&
        ((bc_pool_enabled && info.props.is_block) ||
         (rgba128_pool_enabled && image_ci.format == vk::Format::eR32G32B32A32Uint));
    backing->image.Create(image_ci);
    // A hit reuses existing driver/VMA memory and must not be counted as a
    // fresh image_alloc_bc_mib allocation in future performance logs.
    if (Vulkan::MaliPerfStats::Enabled() && !backing->image.reused_from_pool)
        Vulkan::MaliPerfStats::RecordImageAllocation(info.props.is_block,
            info.pixel_format == vk::Format::eR32G32B32A32Uint,
            static_cast<uint64_t>(backing->image.size_bytes));
    if (Vulkan::MaliVisualTrace::Enabled(instance.GetPhysicalDevice().getProperties().vendorID)) {
        const auto n = Vulkan::MaliVisualTrace::Add(Vulkan::MaliVisualTrace::Counts::images_created);
        if (Vulkan::MaliVisualTrace::Sample(n))
            std::printf("GOW3_MALI_VISUAL event=image_create seq=%llu uid=%llu guest=%#llx size=%ux%ux%u guest_format=%s physical=%s mips=%u layers=%u depth=%d stencil=%d\n",
                        (unsigned long long)n, (unsigned long long)image_uid,
                        (unsigned long long)info.guest_address,
                        info.size.width, info.size.height, info.size.depth,
                        vk::to_string(info.pixel_format).c_str(),
                        vk::to_string(image_ci.format).c_str(),
                        image_ci.mipLevels, image_ci.arrayLayers,
                        int(info.props.is_depth), int(info.props.has_stencil));
    }

    Vulkan::SetObjectName(instance.GetDevice(), GetImage(),
                          "Image {}x{}x{} {} {} {:#x}:{:#x} L:{} M:{} S:{}", info.size.width,
                          info.size.height, info.size.depth, AmdGpu::NameOf(info.tile_mode),
                          vk::to_string(info.pixel_format), info.guest_address, info.guest_size,
                          info.resources.layers, info.resources.levels, info.num_samples);
}

Image::~Image() = default;

ImageView& Image::FindView(const ImageViewInfo& view_info, bool ensure_guest_samples) {
    if (ensure_guest_samples && backing->num_samples > 1 != info.num_samples > 1) {
        runtime->SetBackingSamples(this, info.num_samples);
    }
    const auto& view_infos = backing->image_view_infos;
    if (backing->last_view < view_infos.size() && view_infos[backing->last_view] == view_info) {
        return (*slot_image_views)[backing->image_view_ids[backing->last_view]];
    }
    const auto it = std::ranges::find(view_infos, view_info);
    if (it != view_infos.end()) {
        backing->last_view = static_cast<u32>(std::distance(view_infos.begin(), it));
        const auto view_id = backing->image_view_ids[backing->last_view];
        return (*slot_image_views)[view_id];
    }
    const auto view_id = slot_image_views->insert(runtime->GetInstance(), view_info, *this);
    backing->image_view_infos.emplace_back(view_info);
    backing->image_view_ids.emplace_back(view_id);
    return (*slot_image_views)[view_id];
}

void Image::GetBarriers(Barriers& barriers, vk::ImageLayout dst_layout, vk::AccessFlags2 dst_mask,
                        vk::PipelineStageFlags2 dst_stage,
                        std::optional<SubresourceRange> subres_range) {
    auto& last_state = backing->state;
    auto& subresource_states = backing->subresource_states;

    const bool needs_partial_transition =
        subres_range &&
        (subres_range->base != SubresourceBase{} || subres_range->extent != info.resources);
    const bool partially_transited = !subresource_states.empty();
    // Include attachment writes: the old three-flag mask would incorrectly
    // classify a color/depth write as a read and could drop a necessary WAR,
    // RAW or WAW barrier. Never elide a barrier involving any of these writes.
    constexpr vk::AccessFlags2 write_flags =
        vk::AccessFlagBits2::eTransferWrite |
        vk::AccessFlagBits2::eShaderWrite |
        vk::AccessFlagBits2::eMemoryWrite |
        vk::AccessFlagBits2::eColorAttachmentWrite |
        vk::AccessFlagBits2::eDepthStencilAttachmentWrite |
        vk::AccessFlagBits2::eHostWrite |
        vk::AccessFlagBits2::eTransformFeedbackWriteEXT;
    const bool upcoming_writes = static_cast<bool>(dst_mask & write_flags);
    // Keep the ORIGINAL attachment-write ordering policy unchanged. Same
    // attachment writes already run within a Vulkan render pass: adding an
    // explicit barrier on every draw would be a major G720 regression.
    // The broader mask above is only for deciding which reads can be elided.
    constexpr vk::AccessFlags2 legacy_hazard_mask =
        vk::AccessFlagBits2::eTransferWrite |
        vk::AccessFlagBits2::eShaderWrite |
        vk::AccessFlagBits2::eMemoryWrite;
    // A full-image access can collapse previously split subresources. Preserve
    // all read-only stages/accesses from those subresources for future writes.
    vk::AccessFlags2 preserved_read_access{};
    vk::PipelineStageFlags2 preserved_read_stages{};
    const auto note_read_elision = [](bool partial) {
        static thread_local u64 total = 0, subresource = 0;
        ++total;
        subresource += partial;
        // One log per 16K saved barriers, without the expensive perf recorder.
        if ((total & 16383ULL) == 0)
            std::printf("GOW3_MALI_IMAGE_RAR_ELIDED count=%llu subresource=%llu\n",
                        (unsigned long long)total, (unsigned long long)subresource);
    };

    if (needs_partial_transition || partially_transited) {
        if (!partially_transited) {
            subresource_states.resize(info.resources.levels * info.resources.layers);
            std::fill(subresource_states.begin(), subresource_states.end(), last_state);
        }

        // In case of partial transition, we need to change the specified subresources only.
        // Otherwise all subresources need to be set to the same state so we can use a full
        // resource transition for the next time.
        const auto mips =
            needs_partial_transition
                ? std::ranges::views::iota(subres_range->base.level,
                                           subres_range->base.level + subres_range->extent.levels)
                : std::views::iota(0u, info.resources.levels);
        const auto layers =
            needs_partial_transition
                ? std::ranges::views::iota(subres_range->base.layer,
                                           subres_range->base.layer + subres_range->extent.layers)
                : std::views::iota(0u, info.resources.layers);

        for (u32 mip : mips) {
            for (u32 layer : layers) {
                // NOTE: these loops may produce a lot of small barriers.
                // If this becomes a problem, we can optimize it by merging adjacent barriers.
                const auto subres_idx = mip * info.resources.layers + layer;
                ASSERT(subres_idx < subresource_states.size());
                auto& state = subresource_states[subres_idx];

                const bool previous_writes = static_cast<bool>(state.access_mask & write_flags);
                if (CanElideReadOnlyImageBarrier(
                        mali_read_only_elision, state.layout == dst_layout,
                        previous_writes, upcoming_writes)) {
                    // Do not emit a read-after-read barrier. Union the source
                    // stages/accesses so the NEXT write still sees every reader.
                    const bool removed_a_barrier = state.access_mask != dst_mask;
                    state.access_mask |= dst_mask;
                    state.pl_stage |= dst_stage;
                    if (!needs_partial_transition) {
                        preserved_read_access |= state.access_mask;
                        preserved_read_stages |= state.pl_stage;
                    }
                    if (removed_a_barrier) note_read_elision(true);
                    continue;
                }
                if (state.layout != dst_layout || state.access_mask != dst_mask ||
                    static_cast<bool>(state.access_mask & legacy_hazard_mask)) {
                    barriers.emplace_back(vk::ImageMemoryBarrier2{
                        .srcStageMask = state.pl_stage,
                        .srcAccessMask = state.access_mask,
                        .dstStageMask = dst_stage,
                        .dstAccessMask = dst_mask,
                        .oldLayout = state.layout,
                        .newLayout = dst_layout,
                        .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
                        .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
                        .image = GetImage(),
                        .subresourceRange{
                            .aspectMask = aspect_mask,
                            .baseMipLevel = mip,
                            .levelCount = 1,
                            .baseArrayLayer = layer,
                            .layerCount = 1,
                        },
                    });
                    state.layout = dst_layout;
                    state.access_mask = dst_mask;
                    state.pl_stage = dst_stage;
                }
            }
        }

        if (!needs_partial_transition) {
            subresource_states.clear();
        }
    } else { // Full resource transition
        const bool previous_writes = static_cast<bool>(last_state.access_mask & write_flags);
        if (CanElideReadOnlyImageBarrier(
                mali_read_only_elision, last_state.layout == dst_layout,
                previous_writes, upcoming_writes)) {
            const bool removed_a_barrier = last_state.access_mask != dst_mask;
            last_state.access_mask |= dst_mask;
            last_state.pl_stage |= dst_stage;
            if (removed_a_barrier) note_read_elision(false);
            return;
        }
        if (last_state.layout == dst_layout && last_state.access_mask == dst_mask &&
            !static_cast<bool>(last_state.access_mask & legacy_hazard_mask)) {
            return;
        }

        barriers.emplace_back(vk::ImageMemoryBarrier2{
            .srcStageMask = last_state.pl_stage,
            .srcAccessMask = last_state.access_mask,
            .dstStageMask = dst_stage,
            .dstAccessMask = dst_mask,
            .oldLayout = last_state.layout,
            .newLayout = dst_layout,
            .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
            .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
            .image = GetImage(),
            .subresourceRange{
                .aspectMask = aspect_mask,
                .baseMipLevel = 0,
                .levelCount = VK_REMAINING_MIP_LEVELS,
                .baseArrayLayer = 0,
                .layerCount = VK_REMAINING_ARRAY_LAYERS,
            },
        });
    }

    last_state.layout = dst_layout;
    last_state.access_mask = dst_mask | preserved_read_access;
    last_state.pl_stage = dst_stage | preserved_read_stages;
}

} // namespace VideoCore
