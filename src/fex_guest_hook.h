/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef GOW3_FEX_GUEST_HOOK_H
#define GOW3_FEX_GUEST_HOOK_H
#include "guest_cpu.h"
#include <stdint.h>
#include <string.h>

/* The FEX syscall trap at an original x86 E8 CALL does not push a return RIP.
 * A trampoline (whether it executes a RET or jumps to the original callee)
 * needs the exact guest CALL stack state. This helper runs in the guest hook's
 * host callback before changing guest RIP. No native/JIT code is patched here. */
static inline int gow3_fex_prepare_guest_call(GuestRegs *regs, uint64_t next_rip) {
    if (!regs || regs->gpr[GUEST_RSP] < sizeof(next_rip))
        return 0;
    const uintptr_t call_rsp = (uintptr_t)(regs->gpr[GUEST_RSP] - sizeof(next_rip));
    memcpy((void *)call_rsp, &next_rip, sizeof(next_rip));
    regs->gpr[GUEST_RSP] = call_rsp;
    return 1;
}
#endif
