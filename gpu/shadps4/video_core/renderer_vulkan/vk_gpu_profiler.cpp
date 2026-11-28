// SPDX-License-Identifier: GPL-2.0-or-later

#include <algorithm>
#include <cstdlib>

#include "video_core/renderer_vulkan/vk_gpu_profiler.h"
#include "video_core/renderer_vulkan/vk_instance.h"
#include "video_core/renderer_vulkan/vk_scheduler.h"

namespace Vulkan {

void GpuProfiler::Init(const Instance& instance, Scheduler& scheduler) {
    const char* env = std::getenv("GOW3_GPU_PROFILE");
    const bool detailed = env && env[0] == '1';
#ifdef __ANDROID__
    const bool sampled = !env && std::getenv("BB_AOT");
#else
    const bool sampled = false;
#endif
    if ((!detailed && !sampled) || instance_ptr || !instance.IsHostQueryResetSupported()) return;
    const auto families = instance.GetPhysicalDevice().getQueueFamilyProperties();
    const auto queue = instance.GetGraphicsQueueFamilyIndex();
    if (queue >= families.size() || !families[queue].timestampValidBits) {
        std::printf("UB2_GPU_PROFILE unavailable=no-timestamps\n");
        return;
    }
    auto* candidate = new GpuProfiler(instance, scheduler, sampled, families[queue].timestampValidBits);
    if (candidate->pool) instance_ptr = candidate;
    else delete candidate;
}

GpuProfiler::GpuProfiler(const Instance& instance, Scheduler& scheduler_, bool sampled_, u32 valid_bits)
    : device{instance.GetDevice()}, scheduler{scheduler_}, sampled{sampled_} {
    if (valid_bits < 64) timestamp_mask = (u64{1} << valid_bits) - 1;
    const vk::QueryPoolCreateInfo info = {
        .queryType = vk::QueryType::eTimestamp,
        .queryCount = NumSlices * SliceQueries,
    };
    auto [result, created] = device.createQueryPoolUnique(info);
    if (result != vk::Result::eSuccess) {
        std::printf("UB2_GPU_PROFILE unavailable=query-pool\n");
        return;
    }
    pool = std::move(created);
    device.resetQueryPool(*pool, 0, NumSlices * SliceQueries);
    period_ns = instance.GetPhysicalDevice().getProperties().limits.timestampPeriod;
    for (auto& k : keys) {
        k.reserve(SliceQueries);
    }
    std::printf("GPU profile: %s (timestamp period %.2f ns)\n",
                sampled ? "sampled 1/64 frames" : "continuous", period_ns);
}

void GpuProfiler::WriteTimestamp(u64 key) {
    if (!Capturing() || paused || used[slice] + 1 >= SliceQueries) {
        return; // the frame's slice is full: the rest of the frame goes to the last label
    }
    // Outside render passes: radv_CmdWriteTimestamp2 crashed inside some. Marks sit where a
    // pass, dispatch or submission ends anyway.
    scheduler.EndRendering();
    const u32 query = slice * SliceQueries + used[slice]++;
    keys[slice].push_back(key);
    current = key;
    scheduler.Record([pool = *pool, query](vk::CommandBuffer cmdbuf) {
        cmdbuf.writeTimestamp2(vk::PipelineStageFlagBits2::eAllCommands, pool, query);
    });
}

void GpuProfiler::BeginFrame() {
    if (sampled) {
        // Only one frame in 64 gets detailed pass timestamps. No extra waits
        // for query results, and no per-pass timestamp work on other frames.
        ++sample_frame;
        if (sample_active) {
            if (used[slice] > 0 && used[slice] < SliceQueries) {
                scheduler.EndRendering();
                const u32 query = slice * SliceQueries + used[slice]++;
                scheduler.Record([pool = *pool, query](vk::CommandBuffer cmdbuf) {
                    cmdbuf.writeTimestamp2(vk::PipelineStageFlagBits2::eAllCommands, pool, query);
                });
                pending[slice] = true;
                ticks[slice] = scheduler.CurrentTick();
            }
            sample_active = false;
        }
        if ((sample_frame & 63u) != 0) return;
        const u32 next = (slice + 1) % NumSlices;
        if (pending[next] && !scheduler.IsFree(ticks[next])) {
            Print();
            return;
        }
        slice = next;
        if (pending[slice]) Collect(slice);
        if (used[slice]) device.resetQueryPool(*pool, slice * SliceQueries, used[slice]);
        used[slice] = 0;
        keys[slice].clear();
        pending[slice] = false;
        sample_active = true;
        Print();
        return;
    }
    // Close the frame: one more timestamp without a label.
    if (!paused && used[slice] > 0 && used[slice] < SliceQueries) {
        scheduler.EndRendering();
        const u32 query = slice * SliceQueries + used[slice]++;
        scheduler.Record([pool = *pool, query](vk::CommandBuffer cmdbuf) {
            cmdbuf.writeTimestamp2(vk::PipelineStageFlagBits2::eAllCommands, pool, query);
        });
        pending[slice] = true;
        ticks[slice] = scheduler.CurrentTick();
    }
    // The oldest slice, four frames back. While the GPU has not finished it (or its command
    // buffer is not even submitted), its queries can be neither read nor reset: skip this
    // frame's timestamps instead of waiting, which deadlocked during video playback.
    const u32 next = (slice + 1) % NumSlices;
    paused = pending[next] && !scheduler.IsFree(ticks[next]);
    if (paused) {
        Print();
        return;
    }
    slice = next;
    if (pending[slice]) {
        Collect(slice);
    }
    if (used[slice]) {
        device.resetQueryPool(*pool, slice * SliceQueries, used[slice]);
    }
    used[slice] = 0;
    keys[slice].clear();
    pending[slice] = false;
    Print();
}

void GpuProfiler::Collect(u32 which) {
    const u32 count = used[which];
    std::vector<u64> stamps(count);
    // BeginFrame only collects a slice the GPU has finished, so the results are there.
    const auto result = device.getQueryPoolResults(
        *pool, which * SliceQueries, count, count * sizeof(u64), stamps.data(), sizeof(u64),
        vk::QueryResultFlagBits::e64);
    if (result != vk::Result::eSuccess) {
        return;
    }
    for (u32 i = 0; i + 1 < count; ++i) {
        const double ms = double((stamps[i + 1] - stamps[i]) & timestamp_mask) * period_ns / 1e6;
        auto& total = totals[keys[which][i]];
        total.ms += ms;
        ++total.segments;
    }
    ++frames;
}

void GpuProfiler::Print() {
    const auto now = std::chrono::steady_clock::now();
    if (now - window < std::chrono::seconds(5) || frames == 0) {
        return;
    }
    window = now;
    std::vector<std::pair<u64, Total>> sorted(totals.begin(), totals.end());
    std::ranges::sort(sorted, [](const auto& a, const auto& b) { return a.second.ms > b.second.ms; });
    double sum = 0;
    for (const auto& [key, total] : sorted) {
        sum += total.ms;
    }
    std::printf("GPU profile: %.2f ms/frame over %llu %sframes, %zu labels\n", sum / frames,
                static_cast<unsigned long long>(frames), sampled ? "sampled " : "", sorted.size());
    for (size_t i = 0; i < std::min<size_t>(sorted.size(), 30); ++i) {
        const auto& [key, total] = sorted[i];
        std::printf("  %6.3f ms/frame %5.1f/frame  %s\n", total.ms / frames,
                    double(total.segments) / frames, described[key].c_str());
    }
    totals.clear();
    frames = 0;
}

} // namespace Vulkan
