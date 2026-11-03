#!/usr/bin/env python3
"""Native CPU-dirty 256 KiB summary for SotC 0.1.43 (baseline 0.1.40).

Only accelerates read-only (<CPU, Clear, None>) upload scans whose summary has
NO CPU-dirty pages. Writable bindings, GPU page watchers, guest write faults,
hot FaultGrace pages, DMA sweeps and every GPU readback are unchanged.

All CPU state mutations update a conservative live-word atomic summary under
the original RegionManager mutex. A false positive performs original code;
never skip when any dirty page might remain.
"""
from pathlib import Path
import shutil

def once(source:str, before:str, after:str, label:str)->str:
    count=source.count(before)
    if count!=1:
        raise RuntimeError(f"Dirty summary source drift {label}: {count}")
    return source.replace(before,after)

def patch_cpu_dirty_word_summary(root:Path,gpu:Path)->None:
    root=Path(root)
    gpu=Path(gpu)
    p=gpu/"shadps4/video_core/buffer_cache/region_manager.h"
    s=p.read_text()
    header=root/"ports/sotc/android/sotc_cpu_dirty_word_summary.h"
    if not header.is_file():
        raise RuntimeError("Missing shared dirty-summary header")
    shutil.copy2(header,p.parent/"sotc_cpu_dirty_word_summary.h")
    s=once(s,
        '#include "video_core/sotc_stats.h"\n',
        '#include "video_core/sotc_stats.h"\n#include "video_core/buffer_cache/sotc_cpu_dirty_word_summary.h"\n',
        "native summary include")
    s=once(s,
        '    std::atomic<u64> sweep_words{~0ULL}; // sotc: see TakeSweepWords\n',
        '    std::atomic<u64> sweep_words{~0ULL}; // sotc: see TakeSweepWords\n'
        '    // 64 one-bit summaries for 64 x 256 KiB words: conservative until confirmed clean.\n'
        '    std::atomic<u64> cpu_live_words{~0ULL};\n',
        "conservative initial dirty words")
    s=once(s,
        '''        [[maybe_unused]] u64 raised = 0;
        IterateWords(bounds, [&](u64 index, u64 mask) {
            UpdateStateAndProtection<cpu_op, gpu_op>(write_prot, read_prot, index, mask);
            if constexpr (cpu_op == StateOp::Set) {
                if (write_prot[index]) { // CPU bits that went 0 -> 1
                    raised |= 1ULL << index;
                }
            }
        });
        if constexpr (cpu_op == StateOp::Set) {
            if (raised) {
                sweep_words.fetch_or(raised, std::memory_order_release);
            }
        }''',
        '''        [[maybe_unused]] u64 raised = 0;
        [[maybe_unused]] u64 summary_active = 0, summary_cleared = 0;
        IterateWords(bounds, [&](u64 index, u64 mask) {
            UpdateStateAndProtection<cpu_op, gpu_op>(write_prot, read_prot, index, mask);
            if constexpr (cpu_op != StateOp::None) {
                // Exact state of the entire 256 KiB word, not just the touched pages.
                const u64 bit = 1ULL << index;
                if (cpu[index]) summary_active |= bit;
                else summary_cleared |= bit;
            }
            if constexpr (cpu_op == StateOp::Set) {
                if (write_prot[index]) { // CPU bits that went 0 -> 1
                    raised |= 1ULL << index;
                }
            }
        });
        if constexpr (cpu_op != StateOp::None) {
            SotcDirtyWord::Update(cpu_live_words, summary_active, summary_cleared);
        }
        if constexpr (cpu_op == StateOp::Set) {
            if (raised) {
                sweep_words.fetch_or(raised, std::memory_order_release);
            }
        }''',
        "track CPU changes in ChangeRegionState")
    s=once(s,
        '''        auto& state = GetRegionBits<type>();
        // sotc: every draw synchronizes its buffers here''',
        '''        auto& state = GetRegionBits<type>();
        // Read-only buffer uploads are the overwhelming common case for every draw.
        // If ALL covered 256 KiB words are known free of CPU-dirty pages, the
        // original atomic page-by-page scan and its mutex are unnecessary.
        // Written buffers MUST still run the normal scan to mark GPU pages.
        if constexpr (type == Type::CPU && cpu_op == StateOp::Clear &&
                      gpu_op == StateOp::None) {
            static const bool summary_on = [] {
                const char* v = std::getenv("SOTC_CPU_DIRTY_SUMMARY");
                return !v || v[0] != '0';
            }();
            if (summary_on) {
                const auto bounds = GetBounds(offset, size);
                if (SotcStats::kFpsLog) {
                    SotcStats::cpu_dirty_summary_checks.fetch_add(1, std::memory_order_relaxed);
                }
                if (!SotcDirtyWord::MightContain(cpu_live_words, bounds.start_word,
                                                   bounds.end_word)) {
                    if (SotcStats::kFpsLog) {
                        SotcStats::cpu_dirty_summary_skips.fetch_add(1, std::memory_order_relaxed);
                    }
                    return;
                }
            }
        }
        // sotc: every draw synchronizes its buffers here''',
        "early clean-read-only skip")
    s=once(s,
        '''        [[maybe_unused]] u64 kept_words = 0;
        IterateWords(bounds, [&](u64 index, u64 mask) {''',
        '''        [[maybe_unused]] u64 kept_words = 0;
        [[maybe_unused]] u64 summary_active = 0, summary_cleared = 0;
        IterateWords(bounds, [&](u64 index, u64 mask) {''',
        "summary tracking on readback upload scans")
    s=once(s,
        '''            UpdateStateAndProtection<cpu_op, gpu_op>(write_prot, read_prot, index, mask, keep);
            IteratePages(word, [&](u64 pages_offset, u64 pages_size) {''',
        '''            UpdateStateAndProtection<cpu_op, gpu_op>(write_prot, read_prot, index, mask, keep);
            if constexpr (cpu_op != StateOp::None) {
                const u64 bit = 1ULL << index;
                if (cpu[index]) summary_active |= bit;
                else summary_cleared |= bit;
            }
            IteratePages(word, [&](u64 pages_offset, u64 pages_size) {''',
        "sync live-word state after each upload")
    s=once(s,
        '''        if (end_page) {
            func(cpu_addr + start_page * BYTES_PER_PAGE, (end_page - start_page) * BYTES_PER_PAGE);
        }
        if constexpr (grace_op) {''',
        '''        if (end_page) {
            func(cpu_addr + start_page * BYTES_PER_PAGE, (end_page - start_page) * BYTES_PER_PAGE);
        }
        if constexpr (cpu_op != StateOp::None) {
            SotcDirtyWord::Update(cpu_live_words, summary_active, summary_cleared);
        }
        if constexpr (grace_op) {''',
        "publish summary after original CPU modified scan")
    p.write_text(s)

    stats=gpu/"shadps4/video_core/sotc_stats.h"
    q=stats.read_text()
    marker="inline std::atomic<uint64_t> early_flushes{0};"
    q=once(q,marker,
        'inline std::atomic<uint64_t> cpu_dirty_summary_checks{0}, cpu_dirty_summary_skips{0};\n'
        +marker,
        "profiling counters")
    stats.write_text(q)

    driver=gpu/"shadps4/core/libraries/videoout/driver.cpp"
    d=driver.read_text()
    marker='''            ReportPrintf(report, "SOTC readback finish: %llu for bytes the guest asked\\n",'''
    insertion='''            ReportPrintf(report, "SOTC CPU dirty summary: %llu of %llu clean read-only scans skipped\\n",
                         static_cast<unsigned long long>(
                             SotcStats::cpu_dirty_summary_skips.exchange(0)),
                         static_cast<unsigned long long>(
                             SotcStats::cpu_dirty_summary_checks.exchange(0)));
'''
    d=once(d,marker,insertion+marker,"5-second summary log")
    driver.write_text(d)

    checks=[
        'std::atomic<u64> cpu_live_words{~0ULL}',  # new region starts conservatively dirty
        'type == Type::CPU && cpu_op == StateOp::Clear',
        'gpu_op == StateOp::None',
        'SotcDirtyWord::MightContain',
        'SotcDirtyWord::Update',
        'FaultGrace::Now()',
        'tracker->UpdatePageWatchersForRegion',
        'std::atomic<u64> sweep_words{~0ULL}',
        'ForEachModifiedRange',
    ]
    for wanted in checks:
        if wanted not in s: raise RuntimeError("Lost native guard/feature "+wanted)
    print("SotC 0.1.43: CPU dirty word fast negative scan (read-only), original GPU watches and precise readbacks preserved")

if __name__=="__main__":
    import argparse
    pa=argparse.ArgumentParser()
    pa.add_argument("--root",type=Path,default=Path("."))
    pa.add_argument("--gpu",type=Path,required=True)
    ar=pa.parse_args()
    patch_cpu_dirty_word_summary(ar.root,ar.gpu)
