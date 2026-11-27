#pragma once

#include <cstdint>
#include <cassert>
#include <deque>
#include <utility>

namespace VideoCore {

// Copies retire in submission order, including overlapping guest ranges.
template <typename Payload>
class ReadbackQueue {
public:
    struct Entry {
        std::uint64_t address, size, tick;
        Payload payload;
        bool valid = true;
        bool watched = true; ///< still protects its pages (see ReleaseOutside)
        std::uint64_t image_uid = 0, version = 0, write_epoch = 0;
    };
    bool CanFit(std::uint64_t size) const {
        return entries.size() < 64 && size <= MaxBytes && bytes <= MaxBytes - size;
    }
    std::uint64_t OldestTick() const { return entries.empty() ? 0 : entries.front().tick; }
    std::uint64_t NewestTick() const { return entries.empty() ? 0 : entries.back().tick; }
    bool HasSmallReadback(std::uint64_t tick, std::uint64_t limit) const {
        for (const auto& e : entries)
            if (e.valid && e.watched && e.tick == tick && e.size <= limit) return true;
        return false;
    }
    // Smallest in-order prefix that makes room. Oversized copies use the
    // explicit synchronous fallback; never return an unrelated future tick.
    std::uint64_t RequiredTickForSpace(std::uint64_t size) const {
        if (CanFit(size) || size > MaxBytes) return 0;
        auto remaining_bytes = bytes;
        auto remaining_count = entries.size();
        for (const auto& entry : entries) {
            remaining_bytes -= entry.size;
            --remaining_count;
            if (remaining_count < 64 && remaining_bytes <= MaxBytes - size)
                return entry.tick;
        }
        return 0;
    }
    void Push(std::uint64_t address, std::uint64_t size, std::uint64_t tick, Payload payload,
              std::uint64_t uid = 0, std::uint64_t version = 0, std::uint64_t write_epoch = 0) {
        assert(CanFit(size));
        entries.push_back({address, size, tick, std::move(payload), true, true, uid, version, write_epoch});
        bytes += size;
    }
    // Last overlapping snapshot must be this exact version. Never skip after
    // unwatch/cancel, an overlapping newer image, or any actual GPU write.
    bool HasExactVersion(std::uint64_t address, std::uint64_t size, std::uint64_t tick,
                         std::uint64_t uid, std::uint64_t version, std::uint64_t write_epoch) const {
        if (!size || !uid || !version || !write_epoch) return false;
        for (auto it = entries.rbegin(); it != entries.rend(); ++it) {
            const auto& e = *it;
            if (!Overlaps(e, address, size, true)) continue;
            return e.valid && e.watched && e.address == address && e.size == size &&
                   e.tick == tick && e.image_uid == uid && e.version == version &&
                   e.write_epoch == write_epoch;
        }
        return false;
    }
    /// `exact`: only copies sharing bytes with the range, not just a page (spartanport: for consumers
    /// that read or drop exactly those bytes, e.g. an image upload).
    std::uint64_t RequiredTick(std::uint64_t address, std::uint64_t size, bool exact = false) const {
        std::uint64_t tick = 0;
        for (const auto& entry : entries) {
            if (entry.valid && entry.watched && Overlaps(entry, address, size, exact)) tick = entry.tick;
        }
        return tick;
    }
    template <typename Callback>
    void Cancel(std::uint64_t address, std::uint64_t size, Callback&& cancel, bool exact = false) {
        for (auto& entry : entries) {
            if (entry.valid && Overlaps(entry, address, size, exact)) {
                cancel(entry);
                entry.valid = false;
            }
        }
    }
    /// gow3: a CPU access to [address, address + size) that shares pages with small copies but
    /// not their bytes stops waiting for them: each such copy is unwatched (`release` drops its
    /// page protection) and still published when the GPU is done. Returns the copies released.
    template <typename Release>
    unsigned ReleaseOutside(std::uint64_t address, std::uint64_t size, std::uint64_t max_size,
                            Release&& release) {
        unsigned released = 0;
        for (auto& entry : entries) {
            if (entry.valid && entry.watched && entry.size <= max_size &&
                OverlapsPage(entry, address, size) &&
                !(address < entry.address + entry.size && entry.address < address + size)) {
                release(entry);
                entry.watched = false;
                ++released;
            }
        }
        return released;
    }
    template <typename Ready, typename Complete>
    void Retire(Ready&& ready, Complete&& complete) {
        while (!entries.empty() && ready(entries.front().tick)) {
            complete(entries.front());
            bytes -= entries.front().size;
            entries.pop_front();
        }
    }
    std::uint64_t Bytes() const { return bytes; }

private:
    static bool OverlapsPage(const Entry& entry, std::uint64_t address, std::uint64_t size) {
        if (!size) return false;
        const auto begin = entry.address & ~std::uint64_t{4095};
        const auto end = (entry.address + entry.size + 4095) & ~std::uint64_t{4095};
        return address < end && begin < address + size;
    }
    static bool Overlaps(const Entry& entry, std::uint64_t address, std::uint64_t size, bool exact) {
        if (!exact) return OverlapsPage(entry, address, size);
        return size && address < entry.address + entry.size && entry.address < address + size;
    }
    static constexpr std::uint64_t MaxBytes = 64ull << 20;
    std::deque<Entry> entries;
    std::uint64_t bytes = 0;
};
} // namespace VideoCore
