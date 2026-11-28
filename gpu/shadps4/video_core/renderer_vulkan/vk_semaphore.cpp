// SPDX-FileCopyrightText: Copyright 2020 yuzu Emulator Project
// SPDX-License-Identifier: GPL-2.0-or-later

#include <limits>
#include "video_core/renderer_vulkan/vk_instance.h"
#include "video_core/renderer_vulkan/vk_semaphore.h"

#include "common/assert.h"

namespace Vulkan {

constexpr u64 WAIT_TIMEOUT = std::numeric_limits<u64>::max();

namespace {
// Port of TLOU cf3da741: publish only driver-proven completion, monotonically.
void PublishCompleted(std::atomic<u64>& known, u64 completed) {
    u64 old = known.load(std::memory_order_acquire);
    while (old < completed &&
           !known.compare_exchange_weak(old, completed, std::memory_order_release,
                                        std::memory_order_relaxed)) {}
}
} // namespace

Semaphore::Semaphore(const Instance& instance_) : instance{instance_} {
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
#ifdef __ANDROID__
    const u64 next = CurrentTick();
    if (next && KnownGpuTick() >= next - 1) {
        return;
    }
#endif
    const auto [counter_result, counter] =
        instance.GetDevice().getSemaphoreCounterValue(*semaphore);
    ASSERT_MSG(counter_result == vk::Result::eSuccess,
               "Failed to get master semaphore value: {}", vk::to_string(counter_result));
    PublishCompleted(gpu_tick, counter);
}

void Semaphore::Wait(u64 tick) {
    // No need to wait if the GPU is ahead of the tick
    if (IsFree(tick)) {
        return;
    }
    // Update the GPU tick and try again
    Refresh();
    if (IsFree(tick)) {
        return;
    }

    // If none of the above is hit, fallback to a regular wait
    const vk::SemaphoreWaitInfo wait_info = {
        .semaphoreCount = 1,
        .pSemaphores = &semaphore.get(),
        .pValues = &tick,
    };

    const auto result = instance.GetDevice().waitSemaphores(&wait_info, WAIT_TIMEOUT);
    ASSERT_MSG(result == vk::Result::eSuccess, "GPU semaphore wait failed: {}",
               vk::to_string(result));
    // The successful wait proves this lower bound; querying the driver again is redundant.
    PublishCompleted(gpu_tick, tick);
}

} // namespace Vulkan
