// SPDX-FileCopyrightText: Copyright 2026 shadPS4 Emulator Project
// SPDX-License-Identifier: GPL-2.0-or-later

#include "gow3_toggles.h"
#include <algorithm>
#include <bit>
#include <cstdlib>
#include <cstring>
#include <cstdio>

#include "common/alignment.h"
#include "common/assert.h"
#include "common/types.h"
#include "core/devtools/widget/gpu_memory.h"
#include "video_core/renderer_vulkan/vk_instance.h"
#include "video_core/renderer_vulkan/vk_scheduler.h"
#include "video_core/renderer_vulkan/vk_staging_buffer_pool.h"

// vk_common.h (via vk_instance.h) must define the Vulkan/VMA configuration
// before VMA includes vulkan.h. Match image.cpp and buffer.cpp.
#include <vk_mem_alloc.h>

namespace Vulkan {

using VideoCore::MemoryType;

namespace {

// gow3: staging memory is populated (allocated and cleared) by the kernel on first CPU access,
// ~2 ms per 16 MiB block. Streaming bursts a few seconds apart re-created the blocks trimmed
// in between and copies into them ran at 0.3 GB/s (stutter). Blocks now live 30 s idle, the
// upload ring keeps GOW3_STAGING_KEEP_MB (512) and is populated at startup.
constexpr u64 RING_IDLE_FRAMES = 3000;
constexpr u64 LARGE_IDLE_FRAMES = 3000;
constexpr u64 PREWARM_BLOCKS = 8;
constexpr u64 LARGE_MIN_GRANULARITY = 64_KB;
constexpr u64 BLOCK_SIZE = 16_MB;

u64 RoundAllocationSize(u64 size) {
    const u64 step = std::max(std::bit_floor(size) / 4, LARGE_MIN_GRANULARITY);
    return Common::AlignUp(size, step);
}

} // Anonymous namespace

StagingBufferPool::StagingBufferPool(const Instance& instance_, Scheduler& scheduler_)
    : instance{instance_}, scheduler{scheduler_} {
    const char* env = std::getenv("GOW3_STAGING_KEEP_MB");
    keep_blocks = (env ? std::strtoull(env, nullptr, 10) : 512) * 1_MB / BLOCK_SIZE;
    Ring& ring = rings[u32(MemoryType::HostUncached)];
    for (u64 i = 0; i < PREWARM_BLOCKS; ++i) {
        auto& block = ring.blocks.emplace_back(Block{
            .buffer = std::make_unique<VideoCore::StreamBuffer>(
                instance, scheduler, MemoryType::HostUncached, BLOCK_SIZE),
            .last_used_frame = frame,
        });
        if (!block.buffer->mapped_data.empty()) {
            std::memset(block.buffer->mapped_data.data(), 0, block.buffer->mapped_data.size());
        }
    }
}

StagingBufferPool::~StagingBufferPool() = default;

StagingBufferRef StagingBufferPool::Request(u64 size, MemoryType type, u64 alignment,
                                            bool deferred) {
    Ring& ring = rings[u32(type)];
    if (deferred || size > BLOCK_SIZE) {
        return RequestLarge(size, type, deferred);
    }
    return RequestFromRing(ring, size, alignment, type);
}

StagingBufferRef StagingBufferPool::RequestFromRing(Ring& ring, u64 size, u64 alignment,
                                                    MemoryType type) {
    Block* best{};
    u64 best_offset{};
    for (size_t i = 0; i < ring.blocks.size(); ++i) {
        const size_t index = (ring.current + i) % ring.blocks.size();
        Block* block = &ring.blocks[index];
        if (const auto offset = block->buffer->Reserve(size, alignment, false)) {
            ring.current = index;
            best = block;
            best_offset = *offset;
            break;
        }
    }

    if (!best) {
        ReclaimForAllocation(BLOCK_SIZE);
        best = &ring.blocks.emplace_back(Block{
            .buffer =
                std::make_unique<VideoCore::StreamBuffer>(instance, scheduler, type, BLOCK_SIZE),
            .last_used_frame = frame,
        });
        ring.current = ring.blocks.size() - 1;
        best_offset = *best->buffer->Reserve(size, alignment, false);
    }

    auto& buffer = *best->buffer;
    best->last_used_frame = frame;

    StagingBufferRef ref{
        .buffer = &buffer,
        .offset = best_offset,
        .size = size,
        .type = type,
    };
    if (!buffer.mapped_data.empty()) {
        ref.mapped = buffer.mapped_data.data() + best_offset;
    }
    return ref;
}

StagingBufferRef StagingBufferPool::RequestLarge(u64 size, MemoryType type, bool deferred) {
    auto& cache = large_caches[u32(type)];
    const u64 max_size = std::max(size + size / 4, RoundAllocationSize(size));

    LargeBuffer* best{};
    for (LargeBuffer& entry : cache) {
        const u64 entry_size = entry.buffer->SizeBytes();
        if (entry.held || entry_size < size || entry_size > max_size ||
            !scheduler.IsFree(entry.tick)) {
            continue;
        }
        if (!best || entry_size < best->buffer->SizeBytes()) {
            best = &entry;
        }
    }

    if (!best) {
        ReclaimForAllocation(RoundAllocationSize(size));
        best = &cache.emplace_back(LargeBuffer{
            .buffer = std::make_unique<VideoCore::Buffer>(instance, 0, RoundAllocationSize(size),
                                                          type, "StagingBufferPool:Dedicated"),
            .tick = 0,
            .last_used_frame = frame,
            .held = false,
        });
    }

    best->tick = scheduler.CurrentTick();
    best->last_used_frame = frame;
    best->held = deferred;

    VideoCore::Buffer& buffer = *best->buffer;
    StagingBufferRef ref{
        .buffer = &buffer,
        .offset = 0,
        .size = size,
        .type = type,
    };
    if (!buffer.mapped_data.empty()) {
        ref.mapped = buffer.mapped_data.data();
    }
    return ref;
}

void StagingBufferPool::FreeDeferred(const StagingBufferRef& ref, u64 completed_tick) {
    auto& cache = large_caches[u32(ref.type)];
    const auto it = std::ranges::find_if(
        cache, [&](const LargeBuffer& entry) { return entry.buffer.get() == ref.buffer; });
    ASSERT_MSG(it != cache.end() && it->held, "FreeDeferred on an allocation that is not held");
    // Only callers that have already consumed a completed GPU copy pass
    // a nonzero tick. Other callers retain the original conservative policy.
    ASSERT(!completed_tick || scheduler.GetWorkSemaphore()->IsFree(completed_tick));
    it->held = false;
    it->tick = completed_tick ? completed_tick : scheduler.CurrentTick();
    it->last_used_frame = frame;
}

void StagingBufferPool::ReclaimForAllocation(u64 requested) {
    // Beta 3 contains a G77-specific VMA pressure-reclaim path. Adapt its
    // safe subset to PanVK UMA: only completed, unheld, previous-frame
    // staging allocations. Never flush, wait or run a retirement callback
    // from inside allocation. VMA bytes freed != actual driver headroom.
    static const bool enabled = [this] {
        const char* opt = std::getenv("GOW3_MALI_STAGING_PRESSURE_RECLAIM");
        return opt && opt[0] == '1' && instance.IsIntegrated() &&
               instance.GetPhysicalDevice().getProperties().vendorID == 0x13B5;
    }();
    if (!enabled) return;
    VmaBudget budgets[VK_MAX_MEMORY_HEAPS]{};
    vmaGetHeapBudgets(instance.GetAllocator(), budgets);
    const auto& mem = instance.GetMemoryProperties();
    u64 headroom = 0;
    bool found = false;
    // UMA can expose multiple heaps. Take the least free device-local heap
    // (conservative), never mistake host-only space for GPU headroom.
    for (u32 n=0; n<mem.memoryHeapCount; ++n) {
        if (!(mem.memoryHeaps[n].flags & vk::MemoryHeapFlagBits::eDeviceLocal) ||
            !budgets[n].budget) continue;
        const u64 free = budgets[n].usage < budgets[n].budget
            ? budgets[n].budget-budgets[n].usage : 0;
        headroom = found ? std::min(headroom, free) : free;
        found = true;
    }
    if (!found) return;
    constexpr u64 reserve = 64_MB;
    const u64 target = requested + reserve;
    if (headroom >= target) return;
    const u64 need = std::min<u64>(target-headroom, 128_MB);
    // One poll, then use only confirmed ticks. Do not touch any allocation
    // used in the current frame, even when the GPU tick already completed.
    scheduler.GetWorkSemaphore()->Refresh();
    const auto completed = scheduler.GetWorkSemaphore()->KnownGpuTick();
    const auto current = scheduler.CurrentTick();
    u64 freed = 0;
    for (auto& cache : large_caches) {
        for (size_t n=cache.size(); n-- > 0 && freed < need;) {
            const auto& e = cache[n];
            if (e.held || e.last_used_frame == frame ||
                e.tick >= current || e.tick > completed) continue;
            freed += e.buffer->SizeBytes();
            cache.erase(cache.begin()+n);
        }
    }
    for (auto& ring : rings) {
        for (size_t n=ring.blocks.size(); n-- > 0 && freed < need;) {
            // Keep a warm block per ring. Unlike periodic TrimRing, this
            // pressure path can retire otherwise retained cold blocks.
            if (ring.blocks.size() <= 1) break;
            const auto& e = ring.blocks[n];
            const auto tick = e.buffer->LastTick();
            if (e.last_used_frame == frame || tick >= current || tick > completed) continue;
            freed += e.buffer->SizeBytes();
            ring.blocks.erase(ring.blocks.begin()+n);
            if (n < ring.current) --ring.current;
            else if (n == ring.current) ring.current = 0;
        }
        if (ring.current >= ring.blocks.size()) ring.current = 0;
    }
    if (freed)
        std::printf("GOW3_MALI_STAGING_PRESSURE requested_mib=%.2f headroom_mib=%.2f retired_mib=%.2f\n",
                    requested/1048576.0, headroom/1048576.0, freed/1048576.0);
}

void StagingBufferPool::TickFrame() {
    ++frame;
    for (Ring& ring : rings) {
        TrimRing(ring);
    }
    for (auto& cache : large_caches) {
        TrimLarge(cache);
    }
    PublishStats();
}

void StagingBufferPool::TrimRing(Ring& ring) {
    auto& blocks = ring.blocks;
    for (size_t i = blocks.size(); i-- > 0;) {
        const Block& block = blocks[i];
        if (blocks.size() <= keep_blocks || frame - block.last_used_frame < RING_IDLE_FRAMES ||
            !scheduler.IsFree(block.buffer->LastTick())) {
            continue;
        }
        blocks.erase(blocks.begin() + i);
        if (i < ring.current) {
            --ring.current;
        } else if (i == ring.current) {
            ring.current = 0;
        }
    }
    if (ring.current >= blocks.size()) {
        ring.current = 0;
    }
}

void StagingBufferPool::TrimLarge(std::vector<LargeBuffer>& cache) {
    std::erase_if(cache, [this](const LargeBuffer& entry) {
        return !entry.held && frame - entry.last_used_frame >= LARGE_IDLE_FRAMES &&
               scheduler.IsFree(entry.tick);
    });
}

void StagingBufferPool::PublishStats() const {
    using namespace Core::Devtools::Widget;
    if (!GpuMemoryViewer::IsEnabled()) {
        return;
    }
    static constexpr std::array<const char*, NUM_TYPES> names = {"DeviceLocal", "HostUncached",
                                                                 "HostCached"};
    GpuMemoryGroup group{.name = "Staging"};
    for (size_t i = 0; i < NUM_TYPES; ++i) {
        u64 bytes = 0;
        for (const Block& block : rings[i].blocks) {
            bytes += block.buffer->SizeBytes();
        }
        for (const LargeBuffer& entry : large_caches[i]) {
            bytes += entry.buffer->SizeBytes();
        }
        if (bytes != 0) {
            group.rows.push_back({.name = names[i], .bytes = bytes});
        }
    }
    GpuMemoryViewer::Publish(std::move(group));
}

} // namespace Vulkan
