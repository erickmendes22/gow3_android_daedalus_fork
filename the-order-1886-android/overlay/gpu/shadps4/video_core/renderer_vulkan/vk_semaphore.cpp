// SPDX-FileCopyrightText: Copyright 2020 yuzu Emulator Project
// SPDX-License-Identifier: GPL-2.0-or-later

#include <cstdlib>
#include "video_core/renderer_vulkan/vk_instance.h"
#include "video_core/renderer_vulkan/vk_semaphore.h"

#include "common/assert.h"

namespace Vulkan {

// Never call vkWaitSemaphores with UINT64_MAX in the Android renderer: a GPU
// hang or VK_ERROR_DEVICE_LOST would otherwise keep the render/guest thread
// blocked indefinitely. A bounded wait must fail closed, not keep using a
// device whose timeline failed to advance.
constexpr u64 WAIT_TIMEOUT_NS = 1'000'000'000ULL;
constexpr u32 MAX_WAIT_TIMEOUTS = 5;

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
    u64 this_tick{};
    u64 counter{};
    do {
        this_tick = gpu_tick.load(std::memory_order_acquire);
        auto [counter_result, cntr] = instance.GetDevice().getSemaphoreCounterValue(*semaphore);
        if (counter_result != vk::Result::eSuccess) {
            LOG_CRITICAL(Render_Vulkan, "Vulkan timeline counter failed (GPU lost?): {}",
                         vk::to_string(counter_result));
            std::abort(); // Avoid GPU-dependent Emulator::Shutdown() on a lost device.
        }
        counter = cntr;
        if (counter < this_tick) {
            return;
        }
    } while (!gpu_tick.compare_exchange_weak(this_tick, counter, std::memory_order_release,
                                             std::memory_order_relaxed));
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

    for (u32 timeouts = 0;;) {
        const auto result = instance.GetDevice().waitSemaphores(&wait_info, WAIT_TIMEOUT_NS);
        if (result == vk::Result::eSuccess) {
            break;
        }
        // A driver error (particularly VK_ERROR_DEVICE_LOST) cannot become
        // success on retry. The old code retried forever without recording it.
        if (result != vk::Result::eTimeout) {
            LOG_CRITICAL(Render_Vulkan, "GPU timeline tick {} failed: {}",
                         tick, vk::to_string(result));
            std::abort(); // Do not retry a lost device or recurse into GPU shutdown.
        }
        if (++timeouts >= MAX_WAIT_TIMEOUTS) {
            LOG_CRITICAL(Render_Vulkan, "GPU timeline tick {} did not advance for {} seconds",
                         tick, MAX_WAIT_TIMEOUTS);
            std::abort();
        }
    }
    Refresh();
}

} // namespace Vulkan
