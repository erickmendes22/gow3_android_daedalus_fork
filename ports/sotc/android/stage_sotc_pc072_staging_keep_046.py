#!/usr/bin/env python3
"""Backport ONLY v0.72 host-staging ring prewarm (not v0.71 pow2 buffer policy).

The v0.1.40 pinned SotC GPU already has SOTC_STAGING_KEEP_MB retention,
but it only retains EXISTING blocks: on first streaming burst nothing is
available. PC v0.72 allocates one 16 MiB host block per idle frame, starting
at frame 61, until the opted-in reserve is ready.

Android guardrails:
- OFF by default (0 MiB);
- only host-visible rings, never DeviceLocal / VRAM;
- max 64 MiB PER host-memory ring;
- 1 allocation/frame; no other original upload or readback logic changed.
"""
from pathlib import Path

def once(src, old, new, label):
    if src.count(old)!=1: raise RuntimeError(f"SotC PC staging source changed ({label}): {src.count(old)}")
    return src.replace(old,new)

def patch_staging(gpu:Path):
    path=Path(gpu)/"shadps4/video_core/renderer_vulkan/vk_staging_buffer_pool.cpp"
    source=path.read_text()
    old='''        return static_cast<size_t>((v ? std::strtoull(v, nullptr, 10) : 0ull) / (BlockSize() >> 20));
    }();
    for (size_t type = 0; type < rings.size(); ++type) {
        TrimRing(rings[type], type == u32(MemoryType::DeviceLocal) ? 0 : keep_host_blocks);
    }
    for (auto& cache : large_caches) {'''
    new='''        // Low-memory Android: cap the OPT-IN host reserve at 64 MiB/ring.
        const u64 mb = std::min<u64>(v ? std::strtoull(v, nullptr, 10) : 0ull, 64ull);
        return static_cast<size_t>(mb / (BlockSize() >> 20));
    }();
    for (size_t type = 0; type < rings.size(); ++type) {
        const size_t keep = type == u32(MemoryType::DeviceLocal) ? 0 : keep_host_blocks;
        TrimRing(rings[type], keep);
        // PC v0.72: prewarm host upload/readback ring, one block per type
        // and frame, instead of allocating during the next area transition.
        // OFF by default, no allocation on DeviceLocal/Adreno video memory.
        Ring& ring = rings[type];
        if (frame > 60 && keep && ring.blocks.size() < keep) {
            const SotcStats::FrameTimer timer{SotcStats::FrameAlloc};
            const SotcStats::AllocTrace trace{SotcStats::AllocStagingBlock, BlockSize()};
            ring.blocks.emplace_back(Block{
                .buffer = std::make_unique<VideoCore::StreamBuffer>(
                    instance, scheduler, MemoryType(type), BlockSize()),
                .last_used_frame = frame,
            });
            if (SotcStats::kFpsLog) {
                std::fprintf(stderr, "SOTC staging prewarm: host type %zu block %zu/%zu (%llu MiB)\\n",
                             type, ring.blocks.size(), keep,
                             (unsigned long long)(BlockSize() >> 20));
            }
        }
    }
    for (auto& cache : large_caches) {'''
    source=once(source,old,new,"staging keep/prewarm")
    source=once(source,'#include <cstdlib>','#include <cstdlib>\n#include <cstdio>',"printf include")
    path.write_text(source)
    print("SotC PC v0.72: host staging prewarm opt-in; DeviceLocal stays zero; original size class retained")

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--gpu",type=Path,required=True)
    patch_staging(p.parse_args().gpu)
