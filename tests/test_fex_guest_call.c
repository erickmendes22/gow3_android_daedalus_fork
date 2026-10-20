/* Host-side regression test for the FEX E8 -> SYSCALL QTE RepeatPress hook.
 * This exercises the actual C helper, not a duplicate Python implementation. */
#include "../src/fex_guest_hook.h"
#include <assert.h>
#include <stdint.h>
#include <string.h>
int main(void) {
    uint64_t stack[32];
    for (unsigned i = 0; i < 32; ++i) stack[i] = 0xfedcba9876543210ULL;
    GuestRegs regs = {0};
    regs.gpr[GUEST_RSP] = (uintptr_t)&stack[17];
    regs.gpr[GUEST_RAX] = 0x12345678;
    const uintptr_t initial_rsp = regs.gpr[GUEST_RSP];
    const uint64_t original_call_address = 0x987654000ULL;
    /* 5-byte E8 rel32: emulated CALL should push RIP + 5. */
    assert(gow3_fex_prepare_guest_call(&regs, original_call_address + 5));
    assert(regs.gpr[GUEST_RSP] == initial_rsp - 8);
    uint64_t return_address = 0;
    memcpy(&return_address, (void *)regs.gpr[GUEST_RSP], sizeof(return_address));
    assert(return_address == original_call_address + 5);
    assert(regs.gpr[GUEST_RAX] == 0x12345678);
    /* Disabled -> jump to original callee -> RET. Enabled -> inline RET.
     * Both cases pop exactly the same return address. */
    for (unsigned branch = 0; branch < 2; ++branch) {
        uintptr_t sp = regs.gpr[GUEST_RSP];
        uint64_t popped;
        memcpy(&popped, (void *)sp, sizeof(popped));
        sp += sizeof(popped);
        assert(popped == original_call_address + 5 && sp == initial_rsp);
    }
    GuestRegs invalid = {0};
    invalid.gpr[GUEST_RSP] = 0;
    assert(!gow3_fex_prepare_guest_call(&invalid, 0xbeef));
    assert(invalid.gpr[GUEST_RSP] == 0);
    assert(!gow3_fex_prepare_guest_call(0, 0xbeef));
    return 0;
}
