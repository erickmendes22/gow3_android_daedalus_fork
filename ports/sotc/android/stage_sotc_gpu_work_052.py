#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""SotC 0.1.52: upstream-proven GPU work reductions, isolated to staged SotC.

- Large coherent texture uploads copy on workers while the draw thread continues;
  they are joined by BufferCache::JoinAsyncUploads before Vulkan submission.
  Non-coherent staging keeps the original synchronous copy+flush.
- Repeated HLE fill tables already resident in a single sparse arena are filled
  with vkCmdFillBuffer (u32) or a short seed + device-local doubling copies.
  Original CPU guest backing, readback dirtiness and texture invalidation stay.
Desktop sources are pinned to PC 27f376; patches fail closed if anchors drift.
"""
from pathlib import Path


def swap(value: str, before: str, after: str, what: str) -> str:
    # This copy sequence also occurs in the standalone image-upload helper.
    # Restrict the texture optimization to ObtainBufferForImage, not that helper.
    if what == "async coherent texture staging":
        signature = "std::pair<const Buffer*, u64> BufferCache::ObtainBufferForImage("
        if value.count(signature) != 1:
            raise ValueError("SotC GPU work 052 texture function source drift")
        prefix, body = value.split(signature, 1)
        count = body.count(before)
        if count != 1:
            raise ValueError(f"SotC GPU work 052 {what}: source drift ({count})")
        return prefix + signature + body.replace(before, after, 1)
    count = value.count(before)
    if count != 1:
        raise ValueError(f"SotC GPU work 052 {what}: source drift ({count})")
    return value.replace(before, after, 1)


def patch_gpu_work(gpu: Path) -> None:
    root = gpu / "shadps4/video_core"
    bc = root / "buffer_cache/buffer_cache.cpp"
    c = bc.read_text()
    c = swap(c,
"""    const SotcStats::SplitTexCopyScope copy_split{staging.size};
    memory->CopySparseMemory(device_addr, staging.mapped, staging.size);
    staging.Flush();
    return {staging.buffer, staging.offset};
}""",
"""    const SotcStats::SplitTexCopyScope copy_split{staging.size};
    // Port of PC 2c09916, adapted for this pinned pre-RunGuestCopy renderer.
    // Coherent host memory alone may be written by worker threads without a
    // flush. Every submit waits for JoinAsyncUploads(), installed by 0.1.51.
    static const u64 async_min = [] {
        const char* v = std::getenv("SOTC_TEX_ASYNC_KB");
        return (v ? std::strtoull(v, nullptr, 10) : 512ULL) << 10;
    }();
    if (async_min && staging.size >= async_min && staging.buffer->is_coherent &&
        BbCopy::Enabled()) {
        constexpr u64 Chunk = 1_MB;
        for (u64 offset = 0; offset < staging.size; offset += Chunk) {
            BbCopy::Async([mem = memory, address = device_addr + offset,
                           dest = staging.mapped + offset,
                           n = std::min<u64>(Chunk, staging.size - offset)] {
                mem->CopySparseMemory(address, dest, n);
            });
        }
        async_uploads.store(true, std::memory_order_release);
    } else {
        memory->CopySparseMemory(device_addr, staging.mapped, staging.size);
        staging.Flush();
    }
    return {staging.buffer, staging.offset};
}""", "async coherent texture staging")
    c = swap(c,
"""bool BufferCache::TryWriteThroughFromCpu(VAddr addr, const void* data, u64 size) {
    if (size == 0) {""",
"""bool BufferCache::TryWriteThroughFromCpu(VAddr addr, const void* data, u64 size) {
    return TryFillThroughFromCpu(addr, data, size, size);
}

bool BufferCache::TryFillThroughFromCpu(VAddr addr, const void* data, u64 size, u64 period) {
    if (size == 0) {""", "GPU repeating fill function")
    c = swap(c,
"""    const auto staging = staging_pool.Request(size, MemoryType::HostUncached);
    std::memcpy(staging.mapped, data, size);
    staging.Flush();
    const vk::BufferCopy copy{staging.offset, arena->Offset(addr), size};
    runtime.CopyBuffer(staging.buffer, arena, std::span{&copy, 1});
    RecordCurrentWrite(addr, size);
    return true;
}""",
"""    // Upstream d13bcfa: don't stage 8 MiB of repeated table bytes again.
    // Copy the whole guest backing as above, then generate identical arena
    // contents in stream order. Fallback still works on non-resident ranges.
    const u64 dst = arena->Offset(addr);
    const auto upload = [&](u64 bytes) {
        const auto staging = staging_pool.Request(bytes, MemoryType::HostUncached);
        std::memcpy(staging.mapped, data, bytes);
        staging.Flush();
        const vk::BufferCopy copy{staging.offset, dst, bytes};
        runtime.CopyBuffer(staging.buffer, arena, std::span{&copy, 1});
    };
    if (period == 4 && (dst & 3) == 0 && (size & 3) == 0) {
        u32 value;
        std::memcpy(&value, data, sizeof(value));
        runtime.FillBuffer(arena, dst, size, value);
    } else if (period != 0 && period < size) {
        constexpr u64 SeedTarget = 1_MB;
        const u64 seed = std::min(size, period * std::max<u64>(1, SeedTarget / period));
        upload(seed);
        for (u64 have = seed; have < size;) {
            const u64 n = std::min(have, size - have);
            const vk::BufferCopy copy{dst, dst + have, n};
            runtime.CopyBuffer(arena, arena, std::span{&copy, 1});
            have += n;
        }
    } else {
        upload(size);
    }
    RecordCurrentWrite(addr, size);
    return true;
}""", "GPU resident fill/seed/doubling")
    bc.write_text(c)

    header = root / "buffer_cache/buffer_cache.h"
    h = header.read_text()
    h = swap(h,
"""    bool TryWriteThroughFromCpu(VAddr addr, const void* data, u64 size);""",
"""    bool TryWriteThroughFromCpu(VAddr addr, const void* data, u64 size);
    // SotC 0.1.52: guest bytes are period-sized pattern repeated up to size.
    bool TryFillThroughFromCpu(VAddr addr, const void* data, u64 size, u64 period);""",
             "fill API")
    header.write_text(h)

    shader = root / "renderer_vulkan/vk_shader_hle.cpp"
    s = shader.read_text()
    s = swap(s,
"""    if (!buffer_cache.TryReplaceFromCpu(address, data.data(), count * 4)) {
        return false;
    }
    if (SotcStats::kCmdStats) SotcStats::inv_hle.fetch_add(count * 4, std::memory_order_relaxed);
    rasterizer.InvalidateMemory(address, count * 4);
    return true;""",
"""    // Upstream d13bcfa GPU fill HLE. The backing bytes are still updated.
    // Do not invalidate the resident arena again: that would stage the same
    // 8 MiB table on the following DMA sweep. Invalidate only overlapping
    // texture views; the buffer cache already marked the guest write.
    static const bool fill_gpu = [] {
        const char* v = std::getenv("SOTC_FILL_HLE_GPU");
        return !(v && v[0] == '0');
    }();
    if (fill_gpu) {
        if (!buffer_cache.TryFillThroughFromCpu(address, data.data(), count * 4, src_count * 4)) {
            return false;
        }
        if (SotcStats::kCmdStats) SotcStats::inv_hle.fetch_add(count * 4, std::memory_order_relaxed);
        SotcStats::mem_epoch.fetch_add(1, std::memory_order_relaxed);
        rasterizer.GetTextureCache().InvalidateMemory(address, count * 4);
        return true;
    }
    if (!buffer_cache.TryReplaceFromCpu(address, data.data(), count * 4)) {
        return false;
    }
    if (SotcStats::kCmdStats) SotcStats::inv_hle.fetch_add(count * 4, std::memory_order_relaxed);
    rasterizer.InvalidateMemory(address, count * 4);
    return true;""", "HLE GPU fill call")
    shader.write_text(s)
    print("SotC GPU work 052: async large coherent texture staging + GPU resident HLE table fill")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--gpu", required=True, type=Path)
    patch_gpu_work(p.parse_args().gpu)
