// SPDX-FileCopyrightText: Copyright 2020 yuzu Emulator Project
// SPDX-License-Identifier: GPL-2.0-or-later

#include <limits>
#include <cstdio>
#include <cstdlib>
#include "video_core/renderer_vulkan/vk_instance.h"
#include "video_core/renderer_vulkan/vk_semaphore.h"

#include "common/assert.h"

namespace Vulkan {

constexpr u64 WAIT_TIMEOUT = std::numeric_limits<u64>::max();
thread_local const Semaphore::ReadbackWaitContext* Semaphore::readback_wait_context = nullptr;
namespace {
std::mutex history_registry_mutex;
std::array<Semaphore*, 16> history_registry{};
}

Semaphore::Semaphore(const Instance& instance_) : instance{instance_} {
#ifdef __ANDROID__
    // The Mali bounded-submit scheduler calls Wait frequently. A completed
    // vkWaitSemaphores(tick) already proves ALL <=tick GPU submissions retired;
    // no extra vkGetSemaphoreCounterValue ioctl is needed.
    const char* trace = std::getenv("GOW3_MALI_SUBMIT_HISTORY");
    trace_enabled = trace && trace[0] == '1' &&
                    instance.GetPhysicalDevice().getProperties().vendorID == 0x13B5;
    const char* opt = std::getenv("GOW3_MALI_DIRECT_TIMELINE_WAIT");
    direct_timeline_wait = std::getenv("GOW3_ANDROID_PORT") != nullptr &&
                           instance.GetPhysicalDevice().getProperties().vendorID == 0x13B5 &&
                           (!opt || opt[0] != '0');
#endif
    const vk::StructureChain semaphore_chain = {
        vk::SemaphoreCreateInfo{},
        vk::SemaphoreTypeCreateInfo{
            .semaphoreType = vk::SemaphoreType::eTimeline,
            .initialValue = 0,
        },
    };
    auto [semaphore_result, sem] =
        instance.GetDevice().createSemaphoreUnique(semaphore_chain.get());
    ASSERT_MSG(semaphore_result == vk::Result::eSuccess, "Failed to create master semaphore: {}",
               vk::to_string(semaphore_result));
    semaphore = std::move(sem);
    if (trace_enabled) {
        std::scoped_lock lock{history_registry_mutex};
        for (auto& slot : history_registry) {
            if (!slot) { slot = this; break; }
        }
    }
}

Semaphore::~Semaphore() {
    if (trace_enabled) {
        std::scoped_lock lock{history_registry_mutex};
        for (auto& slot : history_registry)
            if (slot == this) slot = nullptr;
    }
}

void Semaphore::TraceSubmission(const SubmitRecord& record) {
    if (!trace_enabled) return;
    std::scoped_lock lock{trace_mutex};
    trace_records[record.tick % trace_records.size()] = record;
}

void Semaphore::DumpSubmissionHistory(u64 requested) {
    if (!trace_enabled) return;
    DumpLocalSubmissionHistory(requested);
    // The presenter may be the first Vulkan caller to observe a lost
    // device. Capture the main graphics timeline too, without querying
    // the GPU or waiting for a recorder, queue lock, or another trace.
    std::unique_lock registry{history_registry_mutex, std::try_to_lock};
    if (!registry.owns_lock()) return;
    for (auto* peer : history_registry) {
        if (!peer || peer == this || &peer->instance != &instance) continue;
        std::fprintf(stderr, "GOW3_SUBMIT_PEER origin=%p peer=%p\n",
                     static_cast<const void*>(this), static_cast<const void*>(peer));
        peer->DumpLocalSubmissionHistory(peer->KnownGpuTick() + 1);
    }
}

void Semaphore::DumpLocalSubmissionHistory(u64 requested) {
    std::unique_lock lock{trace_mutex, std::try_to_lock};
    if (!lock.owns_lock()) return;
    std::fprintf(stderr, "GOW3_SUBMIT_HISTORY requested=%llu known=%llu current=%llu semaphore=%p\n",
        (unsigned long long)requested, (unsigned long long)KnownGpuTick(),
        (unsigned long long)CurrentTick(), static_cast<const void*>(this));
    for (const auto& rec : trace_records) {
        if (!rec.tick || (rec.tick < requested && requested - rec.tick > 3)) continue;
        std::fprintf(stderr, "GOW3_SUBMIT_RECORD tick=%llu waits=%llu signals=%llu draws=%llu uploads=%llu downloads=%llu items=%llu\n",
            (unsigned long long)rec.tick, (unsigned long long)rec.wait_count,
            (unsigned long long)rec.signal_count, (unsigned long long)rec.draw_count,
            (unsigned long long)rec.upload_bytes, (unsigned long long)rec.download_bytes,
            (unsigned long long)rec.item_count);
        for (u64 i=0; i<rec.wait_count && i<rec.wait_values.size(); ++i)
            std::fprintf(stderr, "GOW3_SUBMIT_WAIT tick=%llu sem=%llx value=%llu\n",
                (unsigned long long)rec.tick, (unsigned long long)rec.wait_handles[i],
                (unsigned long long)rec.wait_values[i]);
        for (size_t kind = 1; kind < rec.categories.size(); ++kind) {
            const auto& s = rec.categories[kind];
            if (!s.count) continue;
            std::fprintf(stderr, "GOW3_SUBMIT_CATEGORY tick=%llu kind=%zu count=%llu hash=%016llx first_seq=%llu first=%llx:%llx:%llx last_seq=%llu last=%llx:%llx:%llx\n",
                (unsigned long long)rec.tick, kind, (unsigned long long)s.count,
                (unsigned long long)s.signature, (unsigned long long)s.first_seq,
                (unsigned long long)s.first.a, (unsigned long long)s.first.b, (unsigned long long)s.first.c,
                (unsigned long long)s.last_seq, (unsigned long long)s.last.a,
                (unsigned long long)s.last.b, (unsigned long long)s.last.c);
        }
        const u64 begin = rec.item_count > rec.items.size() ? rec.item_count - rec.items.size() : 0;
        for (u64 i=begin; i<rec.item_count; ++i) {
            const auto& e = rec.items[i % rec.items.size()];
            std::fprintf(stderr, "GOW3_SUBMIT_WORK tick=%llu seq=%llu kind=%llu a=%llx b=%llx c=%llx\n",
                (unsigned long long)rec.tick, (unsigned long long)i, (unsigned long long)e.kind,
                (unsigned long long)e.a, (unsigned long long)e.b, (unsigned long long)e.c);
        }
    }
}

void Semaphore::Refresh() {
    u64 this_tick{};
    u64 counter{};
    do {
        this_tick = gpu_tick.load(std::memory_order_acquire);
        auto [counter_result, cntr] = instance.GetDevice().getSemaphoreCounterValue(*semaphore);
        if (counter_result != vk::Result::eSuccess) DumpSubmissionHistory(KnownGpuTick() + 1);
        ASSERT_MSG(counter_result == vk::Result::eSuccess,
                   "Failed to get master semaphore value: {}", vk::to_string(counter_result));
        counter = cntr;
        if (counter < this_tick) {
            return;
        }
    } while (!gpu_tick.compare_exchange_weak(this_tick, counter, std::memory_order_release,
                                             std::memory_order_relaxed));
}

void Semaphore::Wait(u64 tick, std::source_location caller) {
    // No need to wait if the GPU is ahead of the tick
    if (IsFree(tick)) {
        return;
    }
    // The original path queries vkGetSemaphoreCounterValue both before and
    // after a wait. With a Mali direct wait, querying that same GPU tick is
    // redundant: waitSemaphores success proves the requested completion.
    if (!direct_timeline_wait) {
        Refresh();
        if (IsFree(tick)) {
            return;
        }
    }

    // If none of the above is hit, fallback to a regular wait
    const vk::SemaphoreWaitInfo wait_info = {
        .semaphoreCount = 1,
        .pSemaphores = &semaphore.get(),
        .pValues = &tick,
    };

    // Long-stall evidence is emitted before an indefinite wait can hide it.
    // A timeout is not success: never publish a tick or skip a dependency.
    const char* trace = std::getenv("GOW3_MALI_GPU_TICK_PROFILE");
    const bool report_stall = trace && trace[0] == '1' &&
        instance.GetPhysicalDevice().getProperties().vendorID == 0x13B5;
    auto result = instance.GetDevice().waitSemaphores(&wait_info,
        report_stall ? u64{500000000} : WAIT_TIMEOUT);
    u32 timeout_count = 0;
    while (result == vk::Result::eTimeout) {
        ++timeout_count;
        if (timeout_count == 1 || (timeout_count % 20) == 0) {
        std::fprintf(stderr, "GOW3_TIMELINE_STALL requested=%llu known=%llu current=%llu caller=%s:%u function=%s semaphore=%p\n",
                     static_cast<unsigned long long>(tick),
                     static_cast<unsigned long long>(KnownGpuTick()),
                     static_cast<unsigned long long>(CurrentTick()),
                     caller.file_name(), caller.line(), caller.function_name(),
                     static_cast<const void*>(this));
        }
        // Timeout is incomplete, not lost. Retry an actual driver wait;
        // never publish a completion or retry after VK_ERROR_DEVICE_LOST.
        result = instance.GetDevice().waitSemaphores(&wait_info,
            report_stall ? u64{500000000} : WAIT_TIMEOUT);
    }
    if (result != vk::Result::eSuccess) {
        DumpSubmissionHistory(tick);
        if (const auto* ctx = readback_wait_context) {
            std::fprintf(stderr, "GOW3_READBACK_FAILURE access=%llx size=%llu source=%llu target_tick=%llu image=%llx image_bytes=%llu uid=%llu\n",
                (unsigned long long)ctx->address, (unsigned long long)ctx->size,
                (unsigned long long)ctx->source, (unsigned long long)ctx->tick,
                (unsigned long long)ctx->image_address, (unsigned long long)ctx->image_size,
                (unsigned long long)ctx->image_uid);
        }
        std::fprintf(stderr, "GOW3_TIMELINE_FAILURE result=%d requested=%llu known=%llu current=%llu caller=%s:%u function=%s semaphore=%p\n",
                     int(result), static_cast<unsigned long long>(tick),
                     static_cast<unsigned long long>(KnownGpuTick()),
                     static_cast<unsigned long long>(CurrentTick()),
                     caller.file_name(), caller.line(), caller.function_name(),
                     static_cast<const void*>(this));
    }
    ASSERT_MSG(result == vk::Result::eSuccess, "Timeline wait failed: {}", vk::to_string(result));
    if (direct_timeline_wait) {
        // Only publish ticks actually confirmed by Vulkan. Other threads may
        // complete newer submissions meanwhile; never move the cache backward.
        u64 known = gpu_tick.load(std::memory_order_relaxed);
        while (known < tick &&
               !gpu_tick.compare_exchange_weak(known, tick, std::memory_order_release,
                                               std::memory_order_relaxed)) {
        }
    } else {
        Refresh();
    }
}

} // namespace Vulkan
