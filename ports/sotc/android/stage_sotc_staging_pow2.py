#!/usr/bin/env python3
"""Backport upstream SotC power-of-two staging-large buffer reuse to Android.

Baseline: the exact pinned original renderer used by working SotC 0.1.40.
The 0.1.41 copy-region coalescer is NOT included.

Newer upstream implementation uses size-classed large staging buffers and
reuses free buffers up to 2x request; it eliminates repeated Vulkan buffer
allocations during area/texture streaming without changing any readback
synchronization, GPU submission or data copied. Keep idle cached buffers
conservatively at 64 MiB per Vulkan memory type on mobile (upstream 256 MiB).
Retain the existing scheduler tick / held-buffer safety checks.
"""
from pathlib import Path

def exact(src,old,new,name):
    count=src.count(old)
    if count!=1:
        raise RuntimeError(f"SotC staging pow2 upstream source drift at {name}: {count}")
    return src.replace(old,new)

def patch_staging_pow2(gpu:Path)->None:
    file=Path(gpu)/"shadps4/video_core/renderer_vulkan/vk_staging_buffer_pool.cpp"
    src=file.read_text()
    src=exact(src,
'''u64 RoundAllocationSize(u64 size) {
    const u64 step = std::max(std::bit_floor(size) / 4, LARGE_MIN_GRANULARITY);
    return Common::AlignUp(size, step);
}

} // Anonymous namespace''',
'''u64 RoundAllocationSize(u64 size) {
    const u64 step = std::max(std::bit_floor(size) / 4, LARGE_MIN_GRANULARITY);
    return Common::AlignUp(size, step);
}

// Backported from upstream SotC staging-large size class recycling.
// The original allocator matched request sizes within ~1.25x and created
// many short-lived large VkBuffers during area streaming.
// No readback fences, memory types, or async ownership rules are bypassed.
bool StagingLargePow2() {
    static const bool enabled = [] {
        const char* v = std::getenv("SOTC_STAGING_LARGE_POW2");
        return !v || v[0] != '0';
    }();
    return enabled;
}
u64 StagingLargeKeepBytes() {
    static const u64 bytes = [] {
        const char* v = std::getenv("SOTC_STAGING_LARGE_KEEP_MB");
        // Mobile Adreno can exceed the Vulkan device-local budget.
        // Keep at most 64 MiB of idle staging per memory type, vs upstream 256.
        return (v ? std::strtoull(v, nullptr, 10) : 64ULL) << 20;
    }();
    return bytes;
}

} // Anonymous namespace''',"shared helper anchor")
    src=exact(src,
'''    const u64 alloc_size =
        deferred ? std::bit_ceil(std::max(size, LARGE_MIN_GRANULARITY)) : RoundAllocationSize(size);
    const u64 max_size = deferred ? alloc_size : std::max(size + size / 4, RoundAllocationSize(size));''',
'''    // Deferred readbacks retain their original exact size-class matching.
    // Other large uploads can now reuse a free buffer in the next 2x class.
    const bool pow2 = deferred || StagingLargePow2();
    const u64 alloc_size =
        pow2 ? std::bit_ceil(std::max(size, LARGE_MIN_GRANULARITY)) : RoundAllocationSize(size);
    const u64 max_size = deferred ? alloc_size
                         : pow2   ? alloc_size * 2
                                  : std::max(size + size / 4, RoundAllocationSize(size));''',"large allocation size class")
    src=exact(src,
'''void StagingBufferPool::TrimLarge(std::vector<LargeBuffer>& cache) {
    std::erase_if(cache, [this](const LargeBuffer& entry) {
        return !entry.held && frame - entry.last_used_frame >= LARGE_IDLE_FRAMES &&
               scheduler.IsFree(entry.tick);
    });
}''',
'''void StagingBufferPool::TrimLarge(std::vector<LargeBuffer>& cache) {
    // Keep the most recently used safe, free large buffers up to a small
    // per-type budget; never evict deferred/held or in-flight GPU buffers.
    u64 keep = StagingLargePow2() ? StagingLargeKeepBytes() : 0;
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
}''',"idle trim safety")
    for needed in (
       '(!scheduler.IsFree(entry.tick) && !unsynchronized)',
       'best->held = deferred;',
       'it->held = false;',
       'it->tick = scheduler.CurrentTick();',
       'std::ranges::sort(cache',
       'SOTC_STAGING_LARGE_POW2'
    ):
        if needed not in src: raise RuntimeError("Lost staging reuse safety contract: "+needed)
    file.write_text(src)
    print("SotC ARM64: staging-large pow2 reuse, 64 MiB idle cap/type, in-flight fence checks preserved")

if __name__=="__main__":
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("--gpu",required=True,type=Path)
    patch_staging_pow2(ap.parse_args().gpu)
