#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""SotC ARM64 command processor -> draw queue CPU fast path.

Observed on Redmagic 8 Elite: 4–5k GPU commands per heavy frame, 35-49 ms
CP CPU, ~35-40 ms draw CPU, back queue at its 512-element limit.

The pinned upstream captures complete 64-dword snapshots for every dirty
register chunk. Every guest SET_*REG remains tracked with identical ordering
and values; use 16-dword chunks on Android to reduce copied unchanged
registers and memory pressure. All chunk sizes divide Regs::NumRegs.

The other source issue is ARM64 spin without a CPU relax instruction:
CpuRelax() is an empty inline function outside x86. BackAlloc spins 4096
times with back_ring full, then sleeps; BackLoop also spins 4096 times
before sleeping when idle. ARM64 yield hint plus bounded (256) polling
allows running the consumer and guest workers. Condition variable and
release/acquire synchronization, queue size, and GPU semantics are untouched.

These optimizations do not disable waits, readbacks, fences, barriers, or draws.
Changes are fail-closed and limited to the staged SotC renderer.
"""
from pathlib import Path


def swap(s: str, old: str, new: str, tag: str, count: int = 1) -> str:
    actual = s.count(old)
    if actual != count:
        raise ValueError(f"SotC CP queue source drift {tag}: expected {count}, found {actual}")
    return s.replace(old, new)


def patch_cp_draw_queue(gpu: Path) -> None:
    root = gpu / "shadps4/video_core/amdgpu"

    header = root / "liverpool.h"
    source = header.read_text()
    source = swap(source,
                  "    static constexpr u32 RegChunkDwords = 64;",
                  """#if defined(__aarch64__)
    // Exact smaller snapshots for the ARM64 CPU-bound PM4 queue.
    // No register is omitted; indices and the draw-thread replay use the
    // very same chunk size below.
    static constexpr u32 RegChunkDwords = 16;
#else
    static constexpr u32 RegChunkDwords = 64;
#endif""",
                  "narrow register-snapshot chunks")
    source = swap(source,
                  "    static constexpr u32 NumRegChunks = Regs::NumRegs / RegChunkDwords;",
                  """    static constexpr u32 NumRegChunks = Regs::NumRegs / RegChunkDwords;
    static_assert(Regs::NumRegs % RegChunkDwords == 0,
                  "SotC snapshots must cover the full register file");
    static_assert(NumRegChunks <= 65536,
                  "SotC snapshot chunk IDs must fit in uint16_t");""",
                  "snapshot bounds and storage")
    header.write_text(source)

    cpp = root / "liverpool.cpp"
    source = cpp.read_text()
    source = swap(source,
                  """static inline void CpuRelax() {
#if defined(__x86_64__) || defined(_M_X64)
    __builtin_ia32_pause();
#endif
}""",
                  """// Never leave ARM64 spinning at full throttle while a consumer, FEX
// guest worker or Vulkan recorder needs the same CPU core.
#if defined(__aarch64__)
static constexpr u32 SotcCpSpinBudget = 256;
#else
static constexpr u32 SotcCpSpinBudget = 4096;
#endif

static inline void CpuRelax() {
#if defined(__x86_64__) || defined(_M_X64)
    __builtin_ia32_pause();
#elif defined(__aarch64__)
    __asm__ volatile("yield" ::: "memory");
#endif
}""",
                  "real ARM64 CPU relax and spin limit")
    source = swap(source,
                  "for (u32 spin = 0; spin < 4096; ++spin) {",
                  "for (u32 spin = 0; spin < SotcCpSpinBudget; ++spin) {",
                  "GPU draw thread idle spin")
    source = swap(source,
                  "if (spin < 4096) {",
                  "if (spin < SotcCpSpinBudget) {",
                  "producer back queue/full drain spin", count=2)
    # These existing lock/predicate waits guarantee correct wakeups after
    # the shorter polling period, without changing ordering or queue depth.
    for mark in ("back_cv.wait_for(", "drain_cv.wait_for(",
                 "back_head.store(head, std::memory_order_seq_cst)",
                 "back_tail.store(tail, std::memory_order_seq_cst)"):
        if mark not in source:
            raise ValueError(f"SotC CP queue lost ordering primitive: {mark}")
    cpp.write_text(source)
    print("SotC Android CPU queue: 16-dword exact register snapshots; ARM64 yield "
          "and 256-spin waits, unchanged synchronization and GPU work")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--gpu", type=Path, required=True)
    patch_cp_draw_queue(p.parse_args().gpu)
