#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Staged Android backport of two measured SotC PC streaming improvements.

Upstream:
  eba9ee46c35 -- power-of-two nondeferred staging reuse
  26e742030b0 -- 256-KiB+ geometry copies off draw thread, joined before submit.

Only the staged SotC Vulkan renderer changes, not GoW3 or guest files.
Android retains 128 MiB on smaller devices or 256 MiB on >=10 GiB RAM
devices, not the desktop v0.76 768 MiB reserve. Incoherent or disabled copy pools keep original
synchronous semantics, and no guest resource operation is skipped.
"""
from pathlib import Path

def swap(text: str, before: str, after: str, label: str) -> str:
    found = text.count(before)
    if found != 1:
        raise ValueError(f"SotC PC 0.76 Android {label}: source drift ({found} matches)")
    return text.replace(before, after, 1)


def patch_pc_streaming(gpu: Path) -> None:
    root = gpu / "shadps4/video_core"
    staging = root / "renderer_vulkan/vk_staging_buffer_pool.cpp"
    s = staging.read_text()
    s = swap(s, "#include <cstdlib>\n",
        "#include <cstdlib>\n#if defined(__ANDROID__)\n#include <unistd.h>\n#endif\n",
        "Android physical RAM probe for upstream staging cap")
    s = swap(s, """} // Anonymous namespace

StagingBufferPool::StagingBufferPool""", """// SotC PC #339: avoid per-frame allocations for different-sized streaming bursts.
// Keep mobile idle memory bounded; buffer ownership/ticks remain checked in RequestLarge.
bool SotcStagingLargePow2() {
    static const bool enabled = [] {
        const char* v = std::getenv("SOTC_STAGING_LARGE_POW2");
        return !v || v[0] != '0';
    }();
    return enabled;
}
u64 SotcStagingLargeKeepBytes() {
    static const u64 bytes = [] {
        const char* v = std::getenv("SOTC_STAGING_LARGE_KEEP_MB");
        // PC v0.76 increased the idle staging reserve after repeated large
        // allocations caused area-transition stalls. On Android keep it bounded
        // to 128 MiB for small devices and 256 MiB only with >=10 GiB physical
        // RAM; unlike desktop, never reserve 768 MiB per memory type.
        u64 fallback_mb = 128;
#if defined(__ANDROID__)
        const long pages = sysconf(_SC_PHYS_PAGES);
        const long page_size = sysconf(_SC_PAGESIZE);
        if (pages > 0 && page_size > 0 &&
            u64(pages) * u64(page_size) >= (10ULL << 30)) {
            fallback_mb = 256;
        }
#endif
        // 'auto' lets the Android launcher explicitly request the RAM-aware
        // default. Numeric overrides including zero remain supported for A/B.
        return (v && v[0] != 'a' ? std::strtoull(v, nullptr, 10) : fallback_mb) << 20;
    }();
    return bytes;
}

} // Anonymous namespace

StagingBufferPool::StagingBufferPool""", "staging power-of-two helpers")
    s = swap(s, """    const u64 alloc_size =
        deferred ? std::bit_ceil(std::max(size, LARGE_MIN_GRANULARITY)) : RoundAllocationSize(size);
    const u64 max_size = deferred ? alloc_size : std::max(size + size / 4, RoundAllocationSize(size));""", """    // Nondeferred large uploads now reuse same-class free allocations, not
    // just allocations within 25 percent of a transient request.
    const bool pow2 = deferred || SotcStagingLargePow2();
    const u64 alloc_size =
        pow2 ? std::bit_ceil(std::max(size, LARGE_MIN_GRANULARITY)) : RoundAllocationSize(size);
    const u64 max_size = deferred ? alloc_size
                         : pow2   ? alloc_size * 2
                                  : std::max(size + size / 4, RoundAllocationSize(size));""",
             "staging allocation classes")
    s = swap(s, """void StagingBufferPool::TrimLarge(std::vector<LargeBuffer>& cache) {
    std::erase_if(cache, [this](const LargeBuffer& entry) {
        return !entry.held && frame - entry.last_used_frame >= LARGE_IDLE_FRAMES &&
               scheduler.IsFree(entry.tick);
    });
}""", """void StagingBufferPool::TrimLarge(std::vector<LargeBuffer>& cache) {
    // Keep the most recently used idle buffers, up to a mobile-size memory cap.
    u64 keep = SotcStagingLargePow2() ? SotcStagingLargeKeepBytes() : 0;
    if (keep != 0) {
        std::ranges::sort(cache, [](const LargeBuffer& a, const LargeBuffer& b) {
            return a.last_used_frame > b.last_used_frame;
        });
    }
    std::erase_if(cache, [this, &keep](const LargeBuffer& entry) {
        if (entry.held || frame - entry.last_used_frame < LARGE_IDLE_FRAMES ||
            !scheduler.IsFree(entry.tick)) {
            return false;
        }
        const u64 bytes = entry.buffer->SizeBytes();
        if (bytes <= keep) {
            keep -= bytes;
            return false;
        }
        return true;
    });
}""", "staging idle eviction")
    staging.write_text(s)

    header = root / "buffer_cache/buffer_cache.h"
    h = header.read_text()
    h = swap(h, """    void SubmitPendingArenaBinds(Vulkan::SubmitInfo& info);""",
        """    void SubmitPendingArenaBinds(Vulkan::SubmitInfo& info);
    // Join copies of guest geometry in coherent staging before submission/readback.
    void JoinAsyncUploads();""", "buffer upload API")
    h = swap(h, """    bool clean_pages_used = false;""",
        """    bool clean_pages_used = false;
    std::atomic<bool> async_uploads{}; // copy workers still writing staging bytes""",
        "buffer upload pending flag")
    header.write_text(h)

    cpp = root / "buffer_cache/buffer_cache.cpp"
    c = cpp.read_text()
    c = swap(c, """BufferCache::~BufferCache() {
    std::free(block_last_use);
}""", """BufferCache::~BufferCache() {
    JoinAsyncUploads();
    std::free(block_last_use);
}""", "wait on buffer cache destruction")
    c = swap(c, """void BufferCache::ApplyDownloads(std::span<const ReadbackItem> pending, const u8* mapped,
                                 u64 mapped_offset) {""", """void BufferCache::ApplyDownloads(std::span<const ReadbackItem> pending, const u8* mapped,
                                 u64 mapped_offset) {
    // Preserve guest memory ordering: pending uploads cannot observe readback writes.
    JoinAsyncUploads();""", "readback data hazard")
    c = swap(c, """        if (copy_batch && copies.size() > 1 && total_size_bytes >= 2_MB && BbCopy::Enabled()) {""", """        // PC 0.76: let large geometry uploads progress on the copy threads while
        // the draw thread records more work. The buffer is coherent, or we
        // use the original synchronous path; CPU writes after this are tracked.
        // Every submit and readback waits for the pending copies before using bytes.
        static const u64 async_min = [] {
            const char* v = std::getenv("SOTC_BUF_ASYNC_KB");
            return (v ? std::strtoull(v, nullptr, 10) : 256ULL) << 10;
        }();
        if (async_min && total_size_bytes >= async_min && staging.buffer->is_coherent &&
            BbCopy::Enabled()) {
            constexpr u64 PieceSize = 512_KB;
            for (const auto& copy : copies) {
                for (u64 done = 0; done < copy.size; done += PieceSize) {
                    BbCopy::Async([mem = memory, source = copy.dstOffset + done,
                                   dest = staging.mapped + copy.srcOffset + done,
                                   n = std::min(PieceSize, copy.size - done)] {
                        mem->CopySparseMemory(source, dest, n);
                    });
                }
            }
            async_uploads.store(true, std::memory_order_release);
        } else if (copy_batch && copies.size() > 1 && total_size_bytes >= 2_MB &&
                   BbCopy::Enabled()) {""", "async geometry upload")
    c = swap(c, """void BufferCache::SubmitPendingArenaBinds(Vulkan::SubmitInfo& info) {""", """void BufferCache::JoinAsyncUploads() {
    if (!async_uploads.load(std::memory_order_acquire))
        return;
    async_uploads.store(false, std::memory_order_release);
    const SotcStats::FrameTimer frame_timer{SotcStats::FrameBuffer};
    BbCopy::WaitAsync();
}

void BufferCache::SubmitPendingArenaBinds(Vulkan::SubmitInfo& info) {
    JoinAsyncUploads();""", "submission fence for upload workers")
    cpp.write_text(c)
    print("SotC PC streaming: bounded pow2 staging + coherent async geometry copies (joined before submit)")

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--gpu", type=Path, required=True)
    patch_pc_streaming(p.parse_args().gpu)
