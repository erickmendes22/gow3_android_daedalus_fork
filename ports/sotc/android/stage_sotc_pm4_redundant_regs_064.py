#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""ARM64 SotC PM4: eliminate byte-identical redundant register writes.

The command processor receives thousands of PM4/draw operations per frame.
A repeated SET_CONTEXT/CONFIG/SH/UCONFIG_REG with the *same exact values*
need not copy those words nor add a dirty register chunk to the draw ring.
Crucially, SET_CONTEXT still executes its trailing NOP/CB/DB extent logic.
No draw, dispatch, PM4 packet, resource barrier or write to guest memory is
removed. The path is OFF by default after the 0.1.64 Android A/B showed no FPS gain;\nSOTC_PM4_REDUNDANT_REGS=1 is a reversible opt-in for controlled trials.\nAn adaptive probe disables this comparison if duplicate rate is low.
"""
from pathlib import Path

HELPER = r'''
// SotC Android 0.1.64: identical PM4 register payloads have no architectural
// effect on the register file. Preserve all SET_CONTEXT extent hint processing.
// The producer's outstanding dirty bits stay untouched on a redundant write.
static bool SotcRedundantRegBlock(const void* dst, const void* src, size_t words) {
#if defined(__aarch64__) && defined(__ANDROID__)
    static const bool requested = [] {
        const char* p = std::getenv("SOTC_PM4_REDUNDANT_REGS");
        // The 0.1.64 Android capture skipped 32.9% of register writes, but
        // command-density-matched frame times did not improve. Avoid charging
        // the extra memcmp on every PM4 packet without demonstrated benefit.
        // Retain explicit opt-in for controlled A/B (SOTC_PM4_REDUNDANT_REGS=1).
        return p && p[0] == '1';
    }();
    static thread_local bool active = true;
    static thread_local u64 probes = 0;
    static thread_local u64 duplicates = 0;
    if (!requested || !active || words == 0 || words > 64) return false;
    const bool equal = std::memcmp(dst, src, words * sizeof(u32)) == 0;
    ++probes;
    duplicates += equal;
    // Low duplicate rates make the extra comparison more expensive than
    // simply copying. Disengage for the rest of this process if below 25%.
    if (probes == 8192 && duplicates * 4 < probes) active = false;
    if (SotcStats::kFpsLog &&
        (probes == 8192 || (active && probes % 32768 == 0))) {
        std::fprintf(stderr,
            "SOTC PM4 SAME-REG: %llu/%llu exact writes skipped (%.1f%%), adaptive=%d\\n",
            static_cast<unsigned long long>(duplicates),
            static_cast<unsigned long long>(probes),
            100.0 * static_cast<double>(duplicates) / probes, int(active));
    }
    return equal;
#else
    return false;
#endif
}

'''

def exact(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise ValueError(f"SotC PM4 redundant-reg: {label} expected 1 anchor, got {n}")
    return text.replace(old, new)

def patch(gpu: Path) -> None:
    source = gpu / "shadps4/video_core/amdgpu/liverpool.cpp"
    s=source.read_text()
    if "SOTC PM4 SAME-REG:" in s:
        raise ValueError("SotC PM4 redundant-reg already staged")
    anchor="void Liverpool::ProcessCommands() {"
    s=exact(s,anchor,HELPER+anchor,"helper before command processor")
    old='''                std::memcpy(&regs.reg_array[reg_addr], payload, (count - 1) * sizeof(u32));
                MarkRegs(reg_addr, count - 1);'''
    new='''                const u32 words = count - 1;
                if (!SotcRedundantRegBlock(&regs.reg_array[reg_addr], payload, words)) {
                    std::memcpy(&regs.reg_array[reg_addr], payload, words * sizeof(u32));
                    MarkRegs(reg_addr, words);
                }'''
    if s.count(old) != 2:
        raise ValueError("SotC PM4 redundant-reg: expected config + context pair")
    s=s.replace(old,new)
    old='''                    std::memcpy(&regs.reg_array[Regs::ShRegWordOffset + set_data->reg_offset],
                                header + 2, set_size);
                    MarkRegs(Regs::ShRegWordOffset + set_data->reg_offset,
                             static_cast<u32>(set_size / 4));'''
    new='''                    const u32 reg_addr = Regs::ShRegWordOffset + set_data->reg_offset;
                    if (!SotcRedundantRegBlock(&regs.reg_array[reg_addr],
                                                header + 2, set_size / sizeof(u32))) {
                        std::memcpy(&regs.reg_array[reg_addr], header + 2, set_size);
                        MarkRegs(reg_addr, static_cast<u32>(set_size / 4));
                    }'''
    s=exact(s,old,new,"shader register write")
    old='''                std::memcpy(&regs.reg_array[Regs::UconfigRegWordOffset + set_data->reg_offset],
                            header + 2, (count - 1) * sizeof(u32));
                MarkRegs(Regs::UconfigRegWordOffset + set_data->reg_offset, count - 1);'''
    new='''                const u32 reg_addr = Regs::UconfigRegWordOffset + set_data->reg_offset;
                const u32 words = count - 1;
                if (!SotcRedundantRegBlock(&regs.reg_array[reg_addr], header + 2, words)) {
                    std::memcpy(&regs.reg_array[reg_addr], header + 2, words * sizeof(u32));
                    MarkRegs(reg_addr, words);
                }'''
    s=exact(s,old,new,"uconfig register write")
    # The exact untouched context-control hints, shader compute-register branch
    # and CLEAR_STATE original must be present after patching.
    for must in ("last_cb_extent[col_buf_id].raw = payload[nop_offset + 1]",
                 "last_db_extent.raw = payload[21]",
                 "mapped_queues[GfxQueueId].cs_state",
                 "regs.SetDefaults();", "MarkRegs(0, Regs::NumRegs);"):
        if must not in s:
            raise ValueError("SotC PM4 redundant-reg: required side effect missing " + must)
    if s.count("SotcRedundantRegBlock(") != 5:
        raise ValueError("SotC PM4 redundant-reg: expected helper + 4 reg classes")
    source.write_text(s)
    print("SotC PM4: adaptive duplicate SET_REG copy/dirty-chunk elision; all side effects preserved")

if __name__ == "__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--gpu",type=Path,required=True)
    patch(p.parse_args().gpu)
