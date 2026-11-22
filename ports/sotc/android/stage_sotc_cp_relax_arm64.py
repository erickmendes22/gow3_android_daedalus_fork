#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Use the AArch64 CPU yield hint in SotC's existing CP/draw wait loops.

The original pinned PC GPU runner has an x86-only CpuRelax() helper. Its
AArch64 body is empty, so full BackRingSize waits spin without a CPU hint.
This patch does NOT alter any spin count (4096), queue capacity (512), ordering,
back_tail/back_head semantics, guest GPU work or CPU ABI. A yield is only a
processor hint, not a sleep, signal, fence, guest scheduler change or TSO.
"""
from pathlib import Path

OLD = """static inline void CpuRelax() {
#if defined(__x86_64__) || defined(_M_X64)
    __builtin_ia32_pause();
#endif
}"""

NEW = """static inline void CpuRelax() {
#if defined(__aarch64__)
    // AArch64 previously ran an empty body in the 4096-iteration wait loops.
    // Yield to sibling hardware threads under a full CP->draw queue without
    // reducing waits, changing ordering, or introducing a host sleep.
    __asm__ __volatile__("yield" ::: "memory");
#elif defined(__x86_64__) || defined(_M_X64)
    __builtin_ia32_pause();
#endif
}"""

def patch(gpu: Path) -> None:
    file = gpu / "shadps4/video_core/amdgpu/liverpool.cpp"
    code = file.read_text()
    if code.count(OLD) != 1:
        raise ValueError("SotC CP relaxation: pinned helper changed; refusing patch")
    for needed in (
        "for (u32 spin = 0; spin < 4096; ++spin)",
        "for (u32 spin = 0; back_tail.load",
        "head - back_tail.load(std::memory_order_acquire) >= BackRingSize",
        "back_head.store(head, std::memory_order_seq_cst)",
        "back_tail.store(tail, std::memory_order_seq_cst)",
    ):
        if needed not in code:
            raise ValueError("SotC CP relaxation: expected queue invariant absent: " + needed)
    file.write_text(code.replace(OLD, NEW))
    print("SotC ARM64 CP/draw wait: yield hint; queue capacity, ring ordering and 4096 spins unchanged")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gpu", type=Path, required=True)
    patch(parser.parse_args().gpu)
