#!/usr/bin/env python3
"""Stage bounded in-flight readback overlap checks into PINNED SotC renderer.

Uses exactly the native 0.1.40 runtime source, not 0.1.41/42/43.
No edits to ReadMemory, Begin/Finish synchronization, staging, GPU protection,
readback range selection, command scheduling, drivers or user preferences.

A readback's conservative [min_item.addr, max(item.addr+size)) hull is built
ONLY after GatherDownloads, before it becomes in flight. Every overlapped
item is contained inside that hull (even if SOTC_RB_HOT is enabled). The
original item-level and copy-level checks remain authoritative.
"""
from pathlib import Path
import shutil

def once(src:str,old:str,new:str,where:str)->str:
    times=src.count(old)
    if times!=1: raise RuntimeError(f"0.1.44 source drift in {where}: {times}")
    return src.replace(old,new)

def patch_inflight(root:Path,gpu:Path)->None:
    root=Path(root)
    gpu=Path(gpu)
    path=gpu/"shadps4/video_core/buffer_cache/buffer_cache.cpp"
    hpath=gpu/"shadps4/video_core/buffer_cache/buffer_cache.h"
    header=root/"ports/sotc/android/sotc_inflight_readback_bounds.h"
    shutil.copy2(header,path.parent/"sotc_inflight_readback_bounds.h")
    src=path.read_text()
    src=once(src,
        '#include "video_core/buffer_cache/buffer_cache.h"\n',
        '#include "video_core/buffer_cache/buffer_cache.h"\n'
        '#include "video_core/buffer_cache/sotc_inflight_readback_bounds.h"\n',
        "include helper")
    src=once(src,
'''    readback.waiting = true;
    inflight_readbacks.push_back(&readback);
    SotcStats::readback_finish.fetch_add(1, std::memory_order_relaxed);''',
'''    readback.waiting = true;
    // A conservative hull of all copied readback items. This also covers the
    // optional speculative HOT items; the original item/copy checks remain.
    readback.inflight_lo = ~VAddr{0};
    readback.inflight_hi = 0;
    for (const auto& item : readback.pending) {
        readback.inflight_lo = std::min(readback.inflight_lo, item.addr);
        readback.inflight_hi = std::max(readback.inflight_hi, item.addr + item.size);
        // Copy ranges can expand to GPU page boundaries; include the actual
        // copied bytes as well, so dependent readbacks never miss them.
        for (const auto& copy : item.copies) {
            const VAddr start = item.arena->cpu_addr + copy.srcOffset;
            readback.inflight_lo = std::min(readback.inflight_lo, start);
            readback.inflight_hi = std::max(readback.inflight_hi, start + copy.size);
        }
    }
    inflight_readbacks.push_back(&readback);
    SotcStats::readback_finish.fetch_add(1, std::memory_order_relaxed);''',
        "publish conservative hull before inflight registration")
    src=once(src,
'''    for (AsyncReadback* readback : inflight_readbacks) {
        for (const auto& item : readback->pending) {
            readback->dirty |= addr < item.addr + item.size && item.addr < addr + size;
        }
    }
}''',
'''    for (AsyncReadback* readback : inflight_readbacks) {
        // Once dirty, the original fallback will re-download; never rescan.
        if (readback->dirty) {
            continue;
        }
        const bool overlaps = SotcInflight::Overlaps(
            addr, size, readback->inflight_lo, readback->inflight_hi - readback->inflight_lo);
        if (SotcStats::kFpsLog) {
            SotcStats::rb_inflight_checks.fetch_add(1, std::memory_order_relaxed);
        }
        if (!overlaps) {
            if (SotcStats::kFpsLog) {
                SotcStats::rb_inflight_pruned.fetch_add(1, std::memory_order_relaxed);
            }
            continue;
        }
        for (const auto& item : readback->pending) {
            if (SotcInflight::Overlaps(addr, size, item.addr, item.size)) {
                readback->dirty = true;
                break;
            }
        }
    }
}''',
        "exact dirty marking equivalence")
    src=once(src,
'''    for (AsyncReadback* readback : inflight_readbacks) {
        for (const auto& item : readback->pending) {
            for (const auto& copy : item.copies) {
                const VAddr start = item.arena->cpu_addr + copy.srcOffset;
                if (addr < start + copy.size && start < addr + size) {
                    return readback;
                }
            }
        }
    }
    return nullptr;
}''',
'''    for (AsyncReadback* readback : inflight_readbacks) {
        if (!SotcInflight::Overlaps(addr, size, readback->inflight_lo,
                                    readback->inflight_hi - readback->inflight_lo)) {
            continue;
        }
        // The hull is only a rejection filter. The original GPU copy-level
        // check determines whether a readback really contains these bytes.
        for (const auto& item : readback->pending) {
            for (const auto& copy : item.copies) {
                const VAddr start = item.arena->cpu_addr + copy.srcOffset;
                if (addr < start + copy.size && start < addr + size) {
                    return readback;
                }
            }
        }
    }
    return nullptr;
}''',
        "exact dependent readback search equivalence")
    for required in (
        "scheduler.WaitSubmitted(readback.tick, false);",
        "scheduler.GetWorkSemaphore()->Wait(readback.tick);",
        "liverpool->SendCommand<true>([this, &readback] { FinishAsyncReadback(readback); });",
        "runtime.CopyBuffer(item.arena, download.buffer, item.copies);",
        "staging_pool.FreeDeferred(download);",
        "ApplyDownloads(readback.pending, download.mapped, download.offset);",
        "SubtractDownloaded(readback.pending);",
        "readback.dirty",
    ):
        if required not in src: raise RuntimeError("Readback safety drift: "+required)
    path.write_text(src)

    src=hpath.read_text()
    src=once(src,
'''        VAddr window_start{};
        u64 window_size{};
        u64 download_offset{};''',
'''        VAddr window_start{};
        u64 window_size{};
        VAddr inflight_lo{~VAddr{0}}; // conservative hull of all pending ReadbackItem ranges
        VAddr inflight_hi{};
        u64 download_offset{};''',
        "two readback hull bounds")
    hpath.write_text(src)

    stats=gpu/"shadps4/video_core/sotc_stats.h"
    t=stats.read_text()
    t=once(t,
        'inline std::atomic<uint64_t> early_flushes{0};',
        'inline std::atomic<uint64_t> rb_inflight_checks{0}, rb_inflight_pruned{0};\n'
        'inline std::atomic<uint64_t> early_flushes{0};',
        "profiling-only reject counters")
    stats.write_text(t)

    driver=gpu/"shadps4/core/libraries/videoout/driver.cpp"
    d=driver.read_text()
    anchor='''            ReportPrintf(report, "SOTC readback finish: %llu for bytes the guest asked\\n",'''
    added='''            ReportPrintf(report, "SOTC inflight bounds: %llu of %llu overlapping-readback scans safely skipped\\n",
                         static_cast<unsigned long long>(
                             SotcStats::rb_inflight_pruned.exchange(0)),
                         static_cast<unsigned long long>(
                             SotcStats::rb_inflight_checks.exchange(0)));
'''
    d=once(d,anchor,added+anchor,"existing 5-second diagnostic")
    driver.write_text(d)
    print("SotC GPU readback 0.1.44: skip non-overlapping inflight scans only; waits and copies byte-identical")

if __name__ == "__main__":
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,default=Path("."))
    parser.add_argument("--gpu",type=Path,required=True)
    args=parser.parse_args()
    patch_inflight(args.root,args.gpu)
