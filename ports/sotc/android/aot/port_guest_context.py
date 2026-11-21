#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Adapt the pinned Bloodborne strict AOT CPU engine to SotC's fiber context ABI.

Source: ducvd89/Bloodborne-Android b6d4cfb6972c84d4029f54765406ec143df3c30e.
FEX is not linked. This script generates source only; it does not prove gameplay.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil

UPSTREAM_PIN = "b6d4cfb6972c84d4029f54765406ec143df3c30e"
REQUIRED = (
    "guest_cpu_aot.cpp", "guest_cpu_aot_hooks.inc", "guest_cpu_native.cpp",
    "guest_cpu_native.h", "guest_cpu_cpuid.h", "guest_cpu_atomics.h",
    "guest_state.h", "host_call_arm64.S",
)

CONTEXT_API = r"""
// SotC's sceFiber HLE expects this exact guest-context ABI.
typedef struct {
    uint64_t gpr[16];
    uint64_t rip;
    uint32_t mxcsr;
    uint16_t fcw;
} SotcGuestContext;
int guest_context_get(SotcGuestContext* out);
int guest_context_set(const SotcGuestContext* in);
"""

CONTEXT_STATE = r"""
// Guest x86-64 state may move between fibers, not the host thread's TLS.
static_assert(sizeof(SotcGuestContext) == 144);
thread_local GuestState* sotc_host_state = nullptr;
thread_local uint64_t sotc_host_return = 0;
thread_local bool sotc_host_replaced = false;
"""

HOST_CALL_CONTEXT = r"""
    GuestState* saved_host_state = sotc_host_state;
    uint64_t saved_host_ret = sotc_host_return;
    bool saved_host_replaced = sotc_host_replaced;
    sotc_host_state = s;
    sotc_host_return = ret;
    sotc_host_replaced = false;
    CallHostFn(s, fn);
    const bool was_replaced = sotc_host_replaced;
    sotc_host_state = saved_host_state;
    sotc_host_return = saved_host_ret;
    sotc_host_replaced = saved_host_replaced;
"""

FIBER_ABI = r"""
// ARM64 AOT semantics: save the state AFTER the guest's host stub RET.
// Unlike the FEX veneer, an AOT stub is not executed as x86 code. Store the
// actual caller RIP and consume its return slot exactly once. A fiber can
// subsequently resume from a return site via --resume-entries.
int guest_context_get(SotcGuestContext* out) {
    if (!out || !sotc_host_state) return 0;
    const GuestState& s = *sotc_host_state;
    std::memcpy(out->gpr, s.gregs, sizeof(out->gpr));
    out->gpr[RSP] += 8;
    out->rip = sotc_host_return;
    out->mxcsr = s.mxcsr;
    out->fcw = s.FCW;
    return 1;
}
int guest_context_set(const SotcGuestContext* in) {
    if (!in || !sotc_host_state) return 0;
    GuestState& s = *sotc_host_state;
    std::memcpy(s.gregs, in->gpr, sizeof(in->gpr));
    s.rip = in->rip;
    s.mxcsr = in->mxcsr;
    s.FCW = in->fcw;
    // The HLE call return and saved result must not overwrite the new fiber.
    // Only guest register state changes: FS/GS remain assigned to this worker.
    sotc_host_replaced = true;
    return 1;
}
"""

def once(s: str, before: str, after: str, what: str) -> str:
    count = s.count(before)
    if count != 1:
        raise ValueError(f"{what}: expected one pinned upstream site, found {count}")
    return s.replace(before, after, 1)

def generate(upstream: Path, out: Path) -> dict:
    cpu = upstream / "cpu"
    header = upstream / "src" / "guest_cpu.h"
    for name in REQUIRED:
        if not (cpu / name).is_file():
            raise FileNotFoundError(f"Pinned Bloodborne CPU file missing: {name}")
    if not header.is_file():
        raise FileNotFoundError("Pinned Bloodborne guest_cpu.h missing")
    main = (cpu / "guest_cpu_aot.cpp").read_text()
    main = once(main, "thread_local Thread* self;\n",
                "thread_local Thread* self;\n" + CONTEXT_STATE,
                "SotC fiber saved state")
    main = once(main,
                "    bbcpu_host_call(fn, &a, &r);\n",
                "    bbcpu_host_call(fn, &a, &r);\n"
                "    if (sotc_host_replaced) return;\n",
                "prevent stale host return overwriting resumed fiber")
    main = once(main, "    CallHostFn(s, fn);\n",
                HOST_CALL_CONTEXT,
                "nested SotC host call context")
    main = once(main,
                "    s->gregs[RSP] = sp + 8;\n    s->rip = ret;\n",
                "    if (!was_replaced) {\n"
                "        s->gregs[RSP] = sp + 8;\n"
                "        s->rip = ret;\n"
                "    }\n",
                "prevent double return on fiber change")
    main = once(main, "extern \"C\" {\n",
                "extern \"C\" {\n" + FIBER_ABI,
                "SotC fiber C ABI")
    if "--tso" in main or "FEXCore" in main:
        raise ValueError("Unexpected TSO/FEX dependency in patched AOT CPU source")
    out.mkdir(parents=True, exist_ok=True)
    for name in REQUIRED:
        if name == "guest_cpu_aot.cpp":
            (out / name).write_text(main)
        else:
            shutil.copy2(cpu / name, out / name)
    header_text = once(header.read_text(), "#pragma GCC visibility pop",
                       CONTEXT_API + "#pragma GCC visibility pop",
                       "SotC guest context ABI exports")
    (out / "guest_cpu.h").write_text(header_text)
    return dict(upstream=str(upstream), output=str(out), upstream_pin=UPSTREAM_PIN,
                fex=False, tso=False, fiber_context_abi=True,
                required_files=list(REQUIRED))

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--upstream", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    print(generate(a.upstream, a.out))

if __name__ == "__main__":
    main()
