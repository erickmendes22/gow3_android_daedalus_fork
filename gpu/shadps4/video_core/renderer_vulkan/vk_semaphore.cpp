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

Semaphore::Semaphore(const Instance& instance_) : instance{instance_} {
#ifdef __ANDROID__
    // The Mali bounded-submit scheduler calls Wait frequently. A completed
    // vkWaitSemaphores(tick) already proves ALL <=tick GPU submissions retired;
    // no extra vkGetSemaphoreCounterValue ioctl is needed.
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
}

Semaphore::~Semaphore() = default;

void Semaphore::Refresh() {
    u64 this_tick{};
    u64 counter{};
    do {
        this_tick = gpu_tick.load(std::memory_order_acquire);
        auto [counter_result, cntr] = instance.GetDevice().getSemaphoreCounterValue(*semaphore);
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
