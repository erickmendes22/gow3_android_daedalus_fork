// SPDX-License-Identifier: GPL-2.0-or-later
// Exact, bounded buffer hazard ranges for a Mali Vulkan buffer barrier.
// Does not infer GPU time: a scoped VkBufferMemoryBarrier2 may or may not
// outperform a global VkMemoryBarrier2 on a specific PanVK version.
#pragma once
#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>
namespace Vulkan {
struct MaliBufferBarrierRegion {
    std::uint64_t buffer;
    std::uint64_t offset;
    std::uint64_t size;
};
class MaliBufferBarrierRegions {
public:
    static constexpr std::size_t Max = 8;
    bool Add(std::uint64_t buffer, std::uint64_t offset, std::uint64_t size) {
        if (overflow_) return false;
        if (!buffer || !size || size > std::numeric_limits<std::uint64_t>::max() - offset) {
            overflow_ = true;
            return false;
        }
        std::uint64_t start = offset, end = offset + size;
        // Coalesce all adjacent/overlapping ranges of the exact same VkBuffer.
        // Repeat after each merge: an added region may bridge two older ranges.
        for (std::size_t i = 0; i < count_;) {
            const auto& existing = regions_[i];
            if (existing.buffer != buffer || end < existing.offset ||
                start > existing.offset + existing.size) {
                ++i;
                continue;
            }
            start = std::min(start, existing.offset);
            end = std::max(end, existing.offset + existing.size);
            regions_[i] = regions_[--count_];
            i = 0;
        }
        if (count_ == Max) {
            overflow_ = true; // use the original global barrier
            return false;
        }
        regions_[count_++] = {buffer, start, end - start};
        return true;
    }
    void Clear() { count_ = 0; overflow_ = false; }
    bool Overflow() const { return overflow_; }
    std::size_t Count() const { return count_; }
    const MaliBufferBarrierRegion& operator[](std::size_t i) const { return regions_[i]; }
private:
    std::array<MaliBufferBarrierRegion, Max> regions_{};
    std::size_t count_{};
    bool overflow_{};
};
} // namespace Vulkan
