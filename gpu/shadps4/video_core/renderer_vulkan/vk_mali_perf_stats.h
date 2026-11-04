// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

// Cheap Mali-only wall-clock stage sampler. The GPU fence stage measures
// host blocking (queue latency + rendering + transfer), not GPU timestamp
// execution. One out of 32 game frames is measured; synchronous dirty-image
// writebacks are always counted because each may drain the Vulkan queue.
// All reports are aggregated: one line per ~5 seconds, no image captures.
#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>

namespace Vulkan {

class MaliPerfStats {
public:
    using Clock = std::chrono::steady_clock;
    using TimePoint = Clock::time_point;

    enum class Stage : unsigned {
        PrepareFrame, FramesAheadWait, AcquireAhb, ReadbackSetup,
        ReadbackSubmit, FenceWait, Invalidate, AhbTotal,
        AhbLock, AhbCopy, AhbUnlock, AhbIpc,
        TextureGc, SyncTextureDownload, Count,
    };

    static bool Enabled() {
        static const bool enabled = [] {
            const char* cpu_present = std::getenv("GOW3_MALI_CPU_PRESENT");
            const char* option = std::getenv("GOW3_MALI_PERF_STATS");
            return cpu_present && cpu_present[0] == '1' && (!option || option[0] != '0');
        }();
        return enabled;
    }

    static bool SamplePresent() {
        if (!Enabled()) return false;
        static std::atomic<uint32_t> frames{0};
        return ((frames.fetch_add(1, std::memory_order_relaxed) + 1) & 31u) == 0;
    }

    static bool SamplePrepare() {
        if (!Enabled()) return false;
        static std::atomic<uint32_t> frames{0};
        return ((frames.fetch_add(1, std::memory_order_relaxed) + 1) & 31u) == 0;
    }

    static bool SampleGc() {
        if (!Enabled()) return false;
        static std::atomic<uint32_t> collections{0};
        return ((collections.fetch_add(1, std::memory_order_relaxed) + 1) & 31u) == 0;
    }

    static void Record(Stage stage, TimePoint start) {
        const auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
                            Clock::now() - start).count();
        if (ns < 0) return;
        auto& row = Get().stages[static_cast<unsigned>(stage)];
        const uint64_t elapsed = static_cast<uint64_t>(ns);
        row.count.fetch_add(1, std::memory_order_relaxed);
        row.total_ns.fetch_add(elapsed, std::memory_order_relaxed);
        uint64_t old_max = row.max_ns.load(std::memory_order_relaxed);
        while (old_max < elapsed &&
               !row.max_ns.compare_exchange_weak(old_max, elapsed,
                                                 std::memory_order_relaxed)) {}
    }

    struct Scoped {
        Stage stage;
        bool active;
        TimePoint start;
        explicit Scoped(Stage stage_, bool active_)
            : stage(stage_), active(active_), start(active_ ? Clock::now() : TimePoint{}) {}
        ~Scoped() {
            if (active) Record(stage, start);
        }
        Scoped(const Scoped&) = delete;
        Scoped& operator=(const Scoped&) = delete;
    };

    // One heartbeat from the present thread; no extra reporter thread and no
    // per-frame printf. Means of each stage are per recorded invocation.
    static void ReportIfDue() {
        if (!Enabled()) return;
        auto& state = Get();
        const uint64_t now_ms = static_cast<uint64_t>(
            std::chrono::duration_cast<std::chrono::milliseconds>(
                Clock::now().time_since_epoch()).count());
        uint64_t last = state.last_report_ms.load(std::memory_order_relaxed);
        if (now_ms < last || now_ms - last < 5000 ||
            !state.last_report_ms.compare_exchange_strong(last, now_ms,
                                                            std::memory_order_relaxed))
            return;
        constexpr std::array names{
            "prepare", "ahead_wait", "acquire_ahb", "rb_setup",
            "rb_submit", "fence_wait", "invalidate", "ahb_total",
            "ahb_lock", "ahb_copy", "ahb_unlock", "ahb_ipc",
            "texture_gc", "texture_sync_download",
        };
        char line[2048]{};
        size_t used = static_cast<size_t>(std::snprintf(
            line, sizeof(line),
            "MALI_PERF_STATS interval_ms=%llu sample=1/32 (except texture_sync_download=all) "
            "values=count/total_ms/avg_ms/max_ms",
            static_cast<unsigned long long>(now_ms - last)));
        for (unsigned i = 0; i < static_cast<unsigned>(Stage::Count); ++i) {
            auto& row = state.stages[i];
            const auto count = row.count.exchange(0, std::memory_order_relaxed);
            const auto total = row.total_ns.exchange(0, std::memory_order_relaxed);
            const auto maximum = row.max_ns.exchange(0, std::memory_order_relaxed);
            if (!count || used >= sizeof(line)) continue;
            const int written = std::snprintf(
                line + used, sizeof(line) - used,
                " %s=%llu/%.2f/%.2f/%.2f",
                names[i], static_cast<unsigned long long>(count),
                total / 1e6, total / (1e6 * count), maximum / 1e6);
            if (written > 0)
                used += std::min(static_cast<size_t>(written), sizeof(line) - used);
        }
        std::printf("%s\n", line);
    }

private:
    struct Counter {
        std::atomic<uint64_t> count{0}, total_ns{0}, max_ns{0};
    };
    struct State {
        std::array<Counter, static_cast<unsigned>(Stage::Count)> stages{};
        std::atomic<uint64_t> last_report_ms{0};
        State() {
            last_report_ms.store(static_cast<uint64_t>(
                std::chrono::duration_cast<std::chrono::milliseconds>(
                    Clock::now().time_since_epoch()).count()), std::memory_order_relaxed);
        }
    };
    static State& Get() {
        static State state{};
        return state;
    }
};

} // namespace Vulkan
