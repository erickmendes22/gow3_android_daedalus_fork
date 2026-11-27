// SPDX-FileCopyrightText: Copyright 2020 yuzu Emulator Project
// SPDX-License-Identifier: GPL-2.0-or-later

#pragma once

#include <atomic>
#include <array>
#include <mutex>
#include <source_location>
#include <condition_variable>
#include <thread>
#include <queue>
#include "common/types.h"
#include "video_core/renderer_vulkan/vk_common.h"

namespace Vulkan {

class Instance;
class Scheduler;

class Semaphore {
public:
    explicit Semaphore(const Instance& instance_);
    ~Semaphore();

    [[nodiscard]] u64 CurrentTick() const noexcept {
        return current_tick.load(std::memory_order_acquire);
    }

    [[nodiscard]] u64 KnownGpuTick() const noexcept {
        return gpu_tick.load(std::memory_order_acquire);
    }

    [[nodiscard]] bool IsFree(u64 tick) const noexcept {
        return KnownGpuTick() >= tick;
    }

    [[nodiscard]] u64 NextTick() noexcept {
        return current_tick.fetch_add(1, std::memory_order_release);
    }

    [[nodiscard]] vk::Semaphore Handle() const noexcept {
        return semaphore.get();
    }

    // Bounded CPU-side submission history. No GPU queries or extra fences.
    struct WorkItem { u64 kind, a, b, c; };
    // Per-category first/last breadcrumbs and rolling signature retain
    // rare operations even when thousands of ordinary draws overwrite the tail.
    struct WorkSummary {
        u64 count{}, first_seq{}, last_seq{}, signature{};
        WorkItem first{}, last{};
    };
    static constexpr size_t WorkKinds = 12;
    struct ReadbackWaitContext {
        u64 address, size, source, tick, image_address, image_size, image_uid;
    };
    class ReadbackWaitScope {
    public:
        explicit ReadbackWaitScope(const ReadbackWaitContext& context) noexcept
            : previous{readback_wait_context} { readback_wait_context = &context; }
        ~ReadbackWaitScope() { readback_wait_context = previous; }
        ReadbackWaitScope(const ReadbackWaitScope&) = delete;
        ReadbackWaitScope& operator=(const ReadbackWaitScope&) = delete;
    private:
        const ReadbackWaitContext* previous;
    };
    static thread_local const ReadbackWaitContext* readback_wait_context;
    struct SubmitRecord {
        u64 tick{}, wait_count{}, signal_count{}, draw_count{}, upload_bytes{}, download_bytes{}, item_count{};
        std::array<WorkItem, 16> items{};
        std::array<WorkSummary, WorkKinds> categories{};
        std::array<u64, 4> wait_values{};
        std::array<u64, 4> wait_handles{};
    };
    void TraceSubmission(const SubmitRecord& record);
    void DumpSubmissionHistory(u64 requested);
    bool TraceEnabled() const noexcept { return trace_enabled; }

    /// Refresh the known GPU tick
    void Refresh();

    /// Waits for a tick to be hit on the GPU
    void Wait(u64 tick, std::source_location caller = std::source_location::current());

protected:
    const Instance& instance;
    vk::UniqueSemaphore semaphore;    ///< Timeline semaphore.
    std::atomic<u64> gpu_tick{0};     ///< Current known GPU tick.
    std::atomic<u64> current_tick{1}; ///< Current logical tick.
    bool trace_enabled = false;
    std::mutex trace_mutex;
    std::array<SubmitRecord, 16> trace_records{};
    bool direct_timeline_wait = false; ///< Mali: a successful timeline wait proves tick completion.
};

} // namespace Vulkan
