#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""SotC ARM64: avoid queuing unchanged guest-register chunks.

The CP owns both regs and last_queued; the draw thread reads neither. The
comparison is against the last PUBLISHED register snapshot, not against
back_regs (which the draw thread mutates). The existing ordered ring and
release/acquire publication remain unchanged. First use of every chunk always
publishes it. This retains 64-dword chunks, all guest draws, and their order.
Set SOTC_REG_SNAPSHOT_MEMO=0 to restore the original queue exactly.
"""
from pathlib import Path


def once(src: str, old: str, new: str, label: str) -> str:
    count = src.count(old)
    if count != 1:
        raise ValueError(f"SotC register snapshot source drift: {label} ({count})")
    return src.replace(old, new)


def patch_sotc_reg_snapshot(gpu: Path) -> None:
    gpu = Path(gpu)
    header = gpu / "shadps4/video_core/amdgpu/liverpool.h"
    s = header.read_text()
    s = once(s,
        "    static constexpr u64 BackRingSize = 512;",
        """    static constexpr u64 BackRingSize = 512;
    // The CP is the sole reader/writer. Never compare against draw-thread
    // back_regs, which may lag queued operations.
    std::vector<u32> sotc_last_queued_regs{};
    std::vector<u8> sotc_queued_chunk_valid{};""",
        "CP-only cached register snapshot")
    header.write_text(s)

    cpp = gpu / "shadps4/video_core/amdgpu/liverpool.cpp"
    s = cpp.read_text()
    s = once(s,
        """        back_ring.resize(BackRingSize);
        dirty_list.reserve(NumRegChunks);
        back_thread =""",
        """        back_ring.resize(BackRingSize);
        dirty_list.reserve(NumRegChunks);
        sotc_last_queued_regs.resize(Regs::NumRegs);
        sotc_queued_chunk_valid.assign(NumRegChunks, 0);
        back_thread =""",
        "snapshot initialized before draw worker starts")

    old = """    op.reg_chunks.clear();
    for (const u16 chunk : dirty_list) {
        const u32* src = &regs.reg_array[u32{chunk} * RegChunkDwords];
        op.reg_chunks.push_back(chunk);
        op.reg_chunks.insert(op.reg_chunks.end(), src, src + RegChunkDwords);
        dirty_chunks[chunk / 64] &= ~(u64{1} << (chunk % 64));
    }
    dirty_list.clear();"""
    new = """    op.reg_chunks.clear();
#if defined(__aarch64__)
    // Only one CP thread writes these arrays, and back_tail prevents ring-slot
    // reuse until ExecuteBackOp completes. The last published value may be
    // ahead of the draw worker; FIFO ordering makes identical deltas redundant.
    static const bool sotc_reg_snapshot_memo = [] {
        const char* v = std::getenv("SOTC_REG_SNAPSHOT_MEMO");
        return !v || v[0] != '0';
    }();
    if (sotc_reg_snapshot_memo) {
        op.reg_chunks.reserve(dirty_list.size() * (RegChunkDwords + 1));
        for (const u16 chunk : dirty_list) {
            const u32 offset = u32{chunk} * RegChunkDwords;
            const u32* src = &regs.reg_array[offset];
            u32* last = sotc_last_queued_regs.data() + offset;
            const bool changed = !sotc_queued_chunk_valid[chunk] ||
                std::memcmp(src, last, RegChunkDwords * sizeof(u32)) != 0;
            if (changed) {
                op.reg_chunks.push_back(chunk);
                op.reg_chunks.insert(op.reg_chunks.end(), src, src + RegChunkDwords);
                std::memcpy(last, src, RegChunkDwords * sizeof(u32));
                sotc_queued_chunk_valid[chunk] = 1;
            }
            dirty_chunks[chunk / 64] &= ~(u64{1} << (chunk % 64));
        }
    } else
#endif
    {
        // Exact 0.1.29 fallback (and the unchanged x86 desktop path).
        for (const u16 chunk : dirty_list) {
            const u32* src = &regs.reg_array[u32{chunk} * RegChunkDwords];
            op.reg_chunks.push_back(chunk);
            op.reg_chunks.insert(op.reg_chunks.end(), src, src + RegChunkDwords);
            dirty_chunks[chunk / 64] &= ~(u64{1} << (chunk % 64));
        }
    }
    dirty_list.clear();"""
    s = once(s, old, new, "exact CP publish-side BackAlloc loop")
    for invariant in (
        "back_tail.store(tail, std::memory_order_seq_cst)",
        "back_head.store(head, std::memory_order_seq_cst)",
        "std::memcpy(&back_regs.reg_array[",
        "rt.flattened_ud_buf.swap(stage.flat);",
        "WaitBackWrites();",
    ):
        if invariant not in s:
            raise ValueError(f"SotC queue ordering invariant missing: {invariant}")
    cpp.write_text(s)
    print("SotC ARM64: skip exactly equal last-published 64-dword register deltas; FIFO unchanged")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gpu", type=Path, required=True)
    patch_sotc_reg_snapshot(ap.parse_args().gpu)
