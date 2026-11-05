// SPDX-License-Identifier: GPL-2.0-or-later
// Daedalus GoW3 Mali: bounded visual provenance from guest images to Android AHB.
// No extra GPU readbacks; works alongside the opt-in stage BMP captures.
// Image UIDs and guest addresses are used to join texture/view/draw/VideoOut events.
#pragma once

#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstdlib>

namespace Vulkan::MaliVisualTrace {

using CountType = std::uint64_t;

struct Counts {
    inline static std::atomic<CountType> images_created{0};
    inline static std::atomic<CountType> unsupported_images{0};
    inline static std::atomic<CountType> views_created{0};
    inline static std::atomic<CountType> views_rejected{0};
    inline static std::atomic<CountType> invalid_sharps{0};
    inline static std::atomic<CountType> empty_sharps{0};
    inline static std::atomic<CountType> null_view_binds{0};
    inline static std::atomic<CountType> textures_bound{0};
    inline static std::atomic<CountType> draws_skipped{0};
    inline static std::atomic<CountType> draws_recorded{0};
    inline static std::atomic<CountType> depth_draws{0};
    inline static std::atomic<CountType> prepared{0};
    inline static std::atomic<CountType> frames_presented{0};
    inline static std::atomic<CountType> ahb_sent{0};
    inline static std::atomic<CountType> ahb_failed{0};
};

inline bool Requested() {
#ifdef __ANDROID__
    static const bool requested = [] {
        const char* value = std::getenv("GOW3_MALI_VISUAL_TRACE");
        return value && value[0] == '1';
    }();
    return requested;
#else
    return false;
#endif
}
inline bool Enabled(std::uint32_t vendor_id) {
    return Requested() && vendor_id == 0x13B5; // ARM Mali only
}
inline CountType Add(std::atomic<CountType>& counter) {
    return counter.fetch_add(1, std::memory_order_relaxed) + 1;
}
inline bool Sample(CountType occurrence) {
    // Startup detail and exponentially spaced later examples; no per-draw log storm.
    return occurrence <= 16 || (occurrence & (occurrence - 1)) == 0;
}
inline CountType Read(const std::atomic<CountType>& counter) {
    return counter.load(std::memory_order_relaxed);
}
inline void ReportPresented(CountType prepared_flip, CountType guest_address,
                            CountType source_uid, std::uint32_t width, std::uint32_t height,
                            bool cpu_copy_ok) {
    if (!Requested()) return;
    const CountType present = Add(Counts::frames_presented);
    if (!Sample(present) && present % 120 != 0 && cpu_copy_ok) return;
    // Counts are cumulative and describe processing through this flip window;
    // they do not prove pixels are correct. Compare staged BMPs and RGB hashes.
    std::printf(
        "GOW3_MALI_VISUAL_SUMMARY present=%llu prepared=%llu guest=%#llx uid=%llu "
        "src=%ux%u cpu_copy_ok=%d images=%llu unsupported_images=%llu views=%llu "
        "view_rejects=%llu empty_sharps=%llu invalid_sharps=%llu null_views=%llu textures_bound=%llu "
        "draws_recorded=%llu depth_draws=%llu draws_skipped=%llu ahb_sent=%llu ahb_failed=%llu\n",
        static_cast<unsigned long long>(present),
        static_cast<unsigned long long>(prepared_flip),
        static_cast<unsigned long long>(guest_address),
        static_cast<unsigned long long>(source_uid), width, height, int(cpu_copy_ok),
        static_cast<unsigned long long>(Read(Counts::images_created)),
        static_cast<unsigned long long>(Read(Counts::unsupported_images)),
        static_cast<unsigned long long>(Read(Counts::views_created)),
        static_cast<unsigned long long>(Read(Counts::views_rejected)),
        static_cast<unsigned long long>(Read(Counts::empty_sharps)),
        static_cast<unsigned long long>(Read(Counts::invalid_sharps)),
        static_cast<unsigned long long>(Read(Counts::null_view_binds)),
        static_cast<unsigned long long>(Read(Counts::textures_bound)),
        static_cast<unsigned long long>(Read(Counts::draws_recorded)),
        static_cast<unsigned long long>(Read(Counts::depth_draws)),
        static_cast<unsigned long long>(Read(Counts::draws_skipped)),
        static_cast<unsigned long long>(Read(Counts::ahb_sent)),
        static_cast<unsigned long long>(Read(Counts::ahb_failed)));
}
} // namespace Vulkan::MaliVisualTrace
