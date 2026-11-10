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
#include <iterator>
#include <cstdio>
#include <cstdlib>
#include <time.h>

namespace Vulkan {

class MaliPerfStats {
public:
    using Clock = std::chrono::steady_clock;
    using TimePoint = Clock::time_point;

    enum class Stage : unsigned {
        PrepareFrame, FramesAheadWait, AcquireAhb, ReadbackSetup,
        ReadbackSubmit, FenceWait, Invalidate, AhbTotal,
        AhbLock, AhbCopy, AhbUnlock, AhbIpc,
        TextureGc, SyncTextureDownload,
        GpuDrawCpu, PipelineLookup,
        DrawTargets, DrawBindings, DrawBeginPass, DrawInputs,
        DrawDescriptors, DrawDynamic, DrawCommands,
        NewGraphicsPipeline, NewComputePipeline, NewShaderModule,
        NewBcImage, NewRgba128Image, NewOtherImage,
        ImageFormatQuery, ImageVkAllocate, Pm4ResumeBlocked, Pm4ResumeWork,
        SubmitMutex, SubmitThrottle, SubmitHostCopies, SubmitQueueDriver,
        PendingTimelineQuery, Pm4SubmitWall,
        Pm4ResumeCpuWork, Pm4ResumeCpuBlocked,
        Count,
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

    // One sample per 256 draws; no clock calls or per-draw logging on
    // the 255 unsampled draws. Covers CPU/GPU command processing even
    // when the menu stops delivering VideoOut frames.
    static bool SampleDraw() {
        if (!Enabled()) return false;
        static thread_local uint32_t draws = 0;
        return (++draws & 255u) == 0;
    }

    // Separate 1/256 sampling stream for DrawRecord() subphases.
    // Keep the existing 1/256 total-draw and PM4 sampling unchanged.
    static bool SampleDrawPhases() {
        if (!Enabled()) return false;
        static thread_local uint32_t draws = 0;
        return (++draws & 255u) == 0;
    }
    static void CountDrawRecorded(uint32_t count) {
        if (Enabled()) Get().draw_commands_recorded.fetch_add(count, std::memory_order_relaxed);
    }
    static void CountGraphicsPipelineBind(bool redundant) {
        if (!Enabled()) return;
        (redundant ? Get().graphics_pipeline_binds_skipped :
                     Get().graphics_pipeline_binds_executed)
            .fetch_add(1, std::memory_order_relaxed);
    }
    static void CountEmptyDrawCandidate() {
        if (Enabled()) Get().empty_draw_candidates.fetch_add(1, std::memory_order_relaxed);
    }

    static bool SampleSubmit() {
        if (!Enabled()) return false;
        static thread_local uint32_t submits = 0;
        return (++submits & 31u) == 0;
    }

    static bool SamplePm4Submit() {
        if (!Enabled()) return false;
        static thread_local uint32_t submits = 0;
        return (++submits & 31u) == 0;
    }

    static bool SamplePm4Resume() {
        if (!Enabled()) return false;
        static thread_local uint32_t resumes = 0;
        return (++resumes & 255u) == 0;
    }

    enum class Pm4WaitReason : unsigned { MemorySemaphore, Rewind, WaitRegMem, Count };
    static void CountPm4Wait(Pm4WaitReason reason) {
        if (!Enabled()) return;
        static thread_local uint32_t yields = 0;
        if ((++yields & 255u) == 0)
            Get().pm4_wait_sampled[static_cast<unsigned>(reason)].fetch_add(
                1, std::memory_order_relaxed);
    }

    static void RecordImageAllocation(bool compressed, bool rgba128, uint64_t bytes) {
        if (!Enabled()) return;
        Get().image_bytes[compressed ? 0u : rgba128 ? 1u : 2u].fetch_add(
            bytes, std::memory_order_relaxed);
    }

    // CPU time excludes sleeping, preemption and blocking Vulkan waits.
    // It is sampled only alongside an existing 1/256 PM4 coroutine resume.
    // Never use this clock as a substitute for GPU timestamps.
    static uint64_t ThreadCpuNs() {
#if defined(__linux__) || defined(__ANDROID__)
        timespec ts{};
        if (clock_gettime(CLOCK_THREAD_CPUTIME_ID, &ts) == 0)
            return uint64_t(ts.tv_sec) * 1000000000ull + uint64_t(ts.tv_nsec);
#endif
        return 0;
    }

    static void RecordDuration(Stage stage, uint64_t elapsed) {
        auto& row = Get().stages[static_cast<unsigned>(stage)];
        row.count.fetch_add(1, std::memory_order_relaxed);
        row.total_ns.fetch_add(elapsed, std::memory_order_relaxed);
        uint64_t old_max = row.max_ns.load(std::memory_order_relaxed);
        while (old_max < elapsed &&
               !row.max_ns.compare_exchange_weak(old_max, elapsed,
                                                 std::memory_order_relaxed)) {}
    }

    static void Record(Stage stage, TimePoint start) {
        const auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
                            Clock::now() - start).count();
        if (ns >= 0) RecordDuration(stage, static_cast<uint64_t>(ns));
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
        constexpr const char* names[]{
            "prepare", "ahead_wait", "acquire_ahb", "rb_setup",
            "rb_submit", "fence_wait", "invalidate", "ahb_total",
            "ahb_lock", "ahb_copy", "ahb_unlock", "ahb_ipc",
            "texture_gc", "texture_sync_download",
            "gpu_draw_cpu", "pipeline_lookup",
            "draw_targets", "draw_bindings", "draw_begin_pass", "draw_inputs",
            "draw_descriptors", "draw_dynamic", "draw_record_commands",
            "graphics_pipeline_new", "compute_pipeline_new", "shader_module_new",
            "image_bc_new", "image_rgba128_new", "image_other_new",
            "image_format_query", "image_vk_allocate", "pm4_resume_blocked", "pm4_resume_work",
            "submit_mutex", "submit_throttle", "submit_host_copy_wait",
            "submit_vk_queue", "pending_timeline_query", "pm4_submit_wall",
            "pm4_resume_cpu_work", "pm4_resume_cpu_blocked",
        };
        static_assert(std::size(names) == static_cast<unsigned>(Stage::Count));
        char line[4096]{};
        size_t used = static_cast<size_t>(std::snprintf(
            line, sizeof(line),
            "MALI_PERF_STATS interval_ms=%llu sample=present,submit=1/32 draw=1/256 "
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
        // Counts are sampled one out of 256 PM4 blocked yields, by reason.
        constexpr const char* wait_names[]{
            "pm4_yield_mem_semaphore_s256", "pm4_yield_rewind_s256", "pm4_yield_wait_regmem_s256"};
        for (unsigned i = 0; i < state.pm4_wait_sampled.size(); ++i) {
            const auto count = state.pm4_wait_sampled[i].exchange(0, std::memory_order_relaxed);
            if (!count || used >= sizeof(line)) continue;
            const int written = std::snprintf(line + used, sizeof(line) - used,
                                               " %s=%llu", wait_names[i],
                                               static_cast<unsigned long long>(count));
            if (written > 0)
                used += std::min(static_cast<size_t>(written), sizeof(line) - used);
        }
        // Report real Vulkan image allocations, not an inferred BC3
        // conversion based only on a rejected alias of guest memory.
        constexpr const char* image_labels[]{
            "image_alloc_bc_mib", "image_alloc_rgba128_mib", "image_alloc_other_mib"};
        for (unsigned i = 0; i < state.image_bytes.size(); ++i) {
            const uint64_t bytes = state.image_bytes[i].exchange(
                0, std::memory_order_relaxed);
            if (!bytes || used >= sizeof(line)) continue;
            const int written = std::snprintf(
                line + used, sizeof(line) - used,
                " %s=%.2f", image_labels[i], bytes / 1048576.0);
            if (written > 0)
                used += std::min(static_cast<size_t>(written), sizeof(line) - used);
        }
        const auto recorded = state.draw_commands_recorded.exchange(0, std::memory_order_relaxed);
        const auto empty = state.empty_draw_candidates.exchange(0, std::memory_order_relaxed);
        const auto binds = state.graphics_pipeline_binds_executed.exchange(
            0, std::memory_order_relaxed);
        const auto skipped = state.graphics_pipeline_binds_skipped.exchange(
            0, std::memory_order_relaxed);
        if (used + 240 < sizeof(line))
            std::snprintf(line + used, sizeof(line) - used,
                          " vk_draw_commands_recorded=%llu empty_draw_candidates=%llu"
                          " gfx_pipeline_binds=%llu gfx_pipeline_binds_skipped=%llu",
                          static_cast<unsigned long long>(recorded),
                          static_cast<unsigned long long>(empty),
                          static_cast<unsigned long long>(binds),
                          static_cast<unsigned long long>(skipped));
        std::printf("%s\n", line);
    }

private:
    struct Counter {
        std::atomic<uint64_t> count{0}, total_ns{0}, max_ns{0};
    };
    struct State {
        std::array<Counter, static_cast<unsigned>(Stage::Count)> stages{};
        std::array<std::atomic<uint64_t>, 3> image_bytes{};
        std::array<std::atomic<uint64_t>, 3> pm4_wait_sampled{};
        std::atomic<uint64_t> last_report_ms{0};
        std::atomic<uint64_t> draw_commands_recorded{0}, empty_draw_candidates{0};
        std::atomic<uint64_t> graphics_pipeline_binds_executed{0}, graphics_pipeline_binds_skipped{0};
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
