// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

#include <atomic>
#include <cstdint>
#include <thread>
#include <mutex>

namespace Vulkan::Detail {

// Wait for the exact recorder-copy sequence requested by the guest-visible
// fence. The recording chunk is already published by KickRecording(true).
// Short completions use a few yields; long waits park instead of burning a
// whole core while the Vulkan recorder or other game workers need CPU time.
// Every release-store that advances completed must notify_all().
inline void WaitForHostCopySequence(std::atomic<std::uint64_t>& completed,
                                    std::uint64_t target) {
    // Android's scheduler yield is relatively costly on the measured
    // 5-10 us handoffs. A bounded local poll gives the already-running
    // recorder time to publish its sequence before we enter the kernel.
    // Never spin indefinitely or weaken the acquire on guest-copy data.
#if defined(__ANDROID__) && defined(__aarch64__)
    for (unsigned i = 0; i < 128; ++i) {
        if (completed.load(std::memory_order_acquire) >= target) return;
        asm volatile("yield" ::: "memory");
    }
#else
    for (unsigned i = 0; i < 4; ++i) {
        if (completed.load(std::memory_order_acquire) >= target) return;
        std::this_thread::yield();
    }
#endif
    for (;;) {
        const auto observed = completed.load(std::memory_order_acquire);
        if (observed >= target) return;
        completed.wait(observed, std::memory_order_acquire);
    }
}

// Recorder copies complete in stream order. A waiter requests a specific
// sequence, not every intermediate copy. Notify only when it can proceed.
// SC publication of completed and waiting_target closes the race in which
// the final copy finishes just as the waiter arms its notification.
class HostCopyCompletion {
public:
    [[nodiscard]] std::uint64_t Value() const {
        return completed.load(std::memory_order_acquire);
    }
    void Publish(std::uint64_t seq) {
        completed.store(seq, std::memory_order_seq_cst);
        const auto target = waiting_target.load(std::memory_order_seq_cst);
        if (target && seq >= target) {
            completed.notify_all();
        }
    }
    void Wait(std::uint64_t target) {
        if (Value() >= target) return;
        // Serialize multiple potential waiters; a producer never takes this
        // lock. A later waiter first checks the already-completed sequence.
        std::unique_lock lock{wait_mutex};
        if (Value() >= target) return;
#if defined(__ANDROID__) && defined(__aarch64__)
        for (unsigned i = 0; i < 128; ++i) {
            if (Value() >= target) return;
            asm volatile("yield" ::: "memory");
        }
#endif
        waiting_target.store(target, std::memory_order_seq_cst);
        for (;;) {
            const auto observed = completed.load(std::memory_order_seq_cst);
            if (observed >= target) break;
            completed.wait(observed, std::memory_order_acquire);
        }
        waiting_target.store(0, std::memory_order_seq_cst);
    }
private:
    alignas(64) std::atomic<std::uint64_t> completed{0};
    alignas(64) std::atomic<std::uint64_t> waiting_target{0};
    std::mutex wait_mutex;
};

} // namespace Vulkan::Detail
