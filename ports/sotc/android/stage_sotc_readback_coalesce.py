#!/usr/bin/env python3
"""Stage lossless GPU-to-host copy-region coalescing on pinned 0.1.34 SotC.

No changes to GPU readback fences, submission, guest memory, stale-page
detection, texture cache, Vulkan drivers, TAA or user preferences.
Only coalesces two vk::BufferCopy ranges when BOTH source and destination
offsets are exactly consecutive, after all GatherDownloads validation.
Profiler-only counters report effectiveness (when SOTC_FPS is enabled).
"""
from pathlib import Path
import shutil

def once(src: str, old: str, new: str, label: str) -> str:
    count=src.count(old)
    if count!=1:
        raise RuntimeError(f"SotC readback coalescer source drift: {label}: {count}")
    return src.replace(old,new)

def patch_readback_coalesce(root: Path, gpu: Path) -> None:
    root=Path(root)
    gpu=Path(gpu)
    bc=gpu/"shadps4/video_core/buffer_cache/buffer_cache.cpp"
    header=root/"ports/sotc/android/sotc_readback_copy_coalesce.h"
    target=bc.parent/"sotc_readback_copy_coalesce.h"
    if not header.is_file():
        raise RuntimeError("Missing portable readback coalescer header")
    shutil.copy2(header,target)
    c=bc.read_text()
    c=once(c, '#include "video_core/buffer_cache/buffer_cache.h"\n',
           '#include "video_core/buffer_cache/buffer_cache.h"\n'
           '#include "video_core/buffer_cache/sotc_readback_copy_coalesce.h"\n',
           "buffer-cache original header")
    # Keep every guest/GPU modification and GPU synchronization unchanged;
    # the compacting operation touches only already-validated VkBufferCopy entries.
    old='''        pending.push_back(std::move(item));
    }
    return total_size_bytes;
}'''
    new='''        // Merge only adjacent VkBufferCopy regions of THIS readback, after
        // GatherDownloads has validated resident and GPU-modified ranges.
        // Every source/destination byte and its ordering remain identical.
        static const bool sotc_merge_readback_copies = [] {
            const char* v = std::getenv("SOTC_RB_COPY_COALESCE");
            return !v || v[0] != '0';
        }();
        if (sotc_merge_readback_copies) {
            const size_t candidates = item.copies.size();
            const size_t joined = SotcReadback::CoalesceAdjacent(item.copies);
            if (SotcStats::kFpsLog) {
                SotcStats::rb_copy_candidates.fetch_add(candidates, std::memory_order_relaxed);
                SotcStats::rb_copy_joined.fetch_add(joined, std::memory_order_relaxed);
            }
        }
        pending.push_back(std::move(item));
    }
    return total_size_bytes;
}'''
    c=once(c,old,new,"single validated GatherDownloads completion")
    for token in ("ReadbackWindow(", "ApplyDownloads(", "SubtractDownloaded(",
                  "FindInflightReadback(", "MarkInflightReadbacksDirty(",
                  "memory_tracker->ForEachDownloadRange<false>("):
        if token not in c:
            raise RuntimeError("Original GPU readback safety code missing: "+token)
    bc.write_text(c)

    stats=gpu/"shadps4/video_core/sotc_stats.h"
    s=stats.read_text()
    s=once(s,
           'inline std::atomic<uint64_t> readback_copies{0};          ///< ranges downloaded\n',
           'inline std::atomic<uint64_t> readback_copies{0};          ///< ranges downloaded\n'
           'inline std::atomic<uint64_t> rb_copy_candidates{0}, rb_copy_joined{0};\n',
           "profiling counters")
    stats.write_text(s)

    driver=gpu/"shadps4/core/libraries/videoout/driver.cpp"
    d=driver.read_text()
    anchor='''            ReportPrintf(report, "SOTC readback finish: %llu for bytes the guest asked\\n",'''
    marker='''            ReportPrintf(report, "SOTC readback copy coalescer: %llu joined of %llu source regions\\n",
                         static_cast<unsigned long long>(
                             SotcStats::rb_copy_joined.exchange(0, std::memory_order_relaxed)),
                         static_cast<unsigned long long>(
                             SotcStats::rb_copy_candidates.exchange(0, std::memory_order_relaxed)));
'''
    d=once(d,anchor,marker+anchor,"FPS profiler readback summary")
    driver.write_text(d)
    print("SotC GPU readback: exact adjacent Vulkan copy coalescer enabled, optout=0; "
          "original fence/heap guard/guest address logic unchanged")

if __name__=="__main__":
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("--gpu",type=Path,required=True)
    ap.add_argument("--root",type=Path,default=Path("."))
    args=ap.parse_args()
    patch_readback_coalesce(args.root,args.gpu)
