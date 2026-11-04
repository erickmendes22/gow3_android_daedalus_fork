#!/usr/bin/env python3
"""SotC 0.1.48: deduplicate *fully covered* in-flight precise GPU readbacks.

Original BeginAsyncReadback performs GatherDownloads before asking about an
in-flight owner; GPU-modified bits stay set until ApplyDownloads, so concurrent
read faults on the same bytes schedule duplicate GPU copies and wait for another
tick. Instead, reuse an already submitted owner ONLY if its recorded copies
cover every byte of the newly requested range. The owner still synchronizes,
applies the current data, handles post-copy GPU writes, and unprotects pages.
No relaxed/stale reads or omitted GPU work. 0 restores the 0.1.45 path.
"""
from pathlib import Path
import shutil

def once(src: str, old: str, new: str, label: str) -> str:
    n = src.count(old)
    if n != 1:
        raise RuntimeError(f"SotC 0.1.48 readback source drift: {label} expected 1, got {n}")
    return src.replace(old,new)

def patch_readback_dedup(gpu: Path, root: Path) -> None:
    directory = gpu / "shadps4/video_core/buffer_cache"
    source = directory / "buffer_cache.cpp"
    header = directory / "buffer_cache.h"
    dest = directory / "sotc_readback_dedup_048.h"
    if dest.exists():
        raise RuntimeError("SotC 0.1.48 readback patch already applied")
    s = source.read_text()
    h = header.read_text()
    h = once(h,
             "    AsyncReadback* FindInflightReadback(VAddr addr, u64 size);",
             "    AsyncReadback* FindInflightReadback(VAddr addr, u64 size);\n"
             "    AsyncReadback* FindCoveringInflightReadback(VAddr addr, u64 size);",
             "declaration")
    s = once(s,
             '#include "video_core/buffer_cache/buffer_cache.h"',
             '#include "video_core/buffer_cache/buffer_cache.h"\n'
             '#include "video_core/buffer_cache/sotc_readback_dedup_048.h"',
             "include")
    needle = """    const u64 total =
        GatherDownloads(arena, window_start, readback.window_size, readback.pending, false);"""
    replacement = """    // A read fault on bytes another guest thread is already downloading must
    // not record a second GPU copy. The existing owner stays alive until its
    // fence and may be marked dirty if newer GPU work overwrites those bytes.
    // Never reuse a partial overlap or a dirty owner.
    static const bool dedup_inflight = [] {
        const char* value = std::getenv("SOTC_RB_INFLIGHT_DEDUP");
        return !value || value[0] != '0';
    }();
    if (dedup_inflight) {
        if (const AsyncReadback* owner =
                FindCoveringInflightReadback(readback.device_addr, readback.size)) {
            readback.tick = owner->tick;
            readback.waiting = true;
            readback.dependent = true;
            // Diagnostic only: no per-fault print or atomic overhead in gameplay.
            static const bool stats = [] {
                const char* value = std::getenv("SOTC_RB_DEDUP_STATS");
                return value && value[0] == '1';
            }();
            if (stats) {
                static std::uint64_t reused = 0;
                if (++reused % 256 == 0) {
                    std::fprintf(stderr, "SOTC RB inflight dedup: %llu duplicate GPU copies avoided\\n",
                                 static_cast<unsigned long long>(reused));
                }
            }
            return;
        }
    }
    const u64 total =
        GatherDownloads(arena, window_start, readback.window_size, readback.pending, false);"""
    s = once(s, needle, replacement, "before duplicate GatherDownloads")
    anchor = """BufferCache::AsyncReadback* BufferCache::FindInflightReadback(VAddr addr, u64 size) {"""
    impl = """BufferCache::AsyncReadback* BufferCache::FindCoveringInflightReadback(VAddr addr, u64 size) {
    // All in-flight owners are command-processor-thread objects, registered
    // only AFTER scheduling their copy and GPU fence. No partial-copy reuse.
    for (AsyncReadback* candidate : inflight_readbacks) {
        if (candidate && !candidate->finished && !candidate->dirty &&
            SotcReadbackDedup::Covers(candidate->pending, addr, size)) {
            return candidate;
        }
    }
    return nullptr;
}

"""
    s = once(s, anchor, impl+anchor, "covering owner implementation")
    shutil.copy2(root/"ports/sotc/android/sotc_readback_dedup_048.h", dest)
    source.write_text(s)
    header.write_text(h)
    print("SotC 0.1.48: fully covered in-flight precise readback reuse; original sync retained")

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--gpu", type=Path, required=True)
    p.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[3])
    args = p.parse_args()
    patch_readback_dedup(args.gpu,args.root)
