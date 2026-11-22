// SPDX-License-Identifier: GPL-3.0-or-later
// Regression: SotC .rodata switch table is *outside* the owning FDE function.
// Compile with upstream bb-recomp/src/jumptable.cpp (after patching).
#include "jumptable.h"
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdio>
#include <vector>

static jt::Ins op(uint64_t pc, uint8_t size, jt::K kind) {
    jt::Ins i{}; i.pc=pc; i.size=size; i.kind=kind; return i;
}
int main() {
    constexpr uint64_t image=0x2b00000000ull;
    constexpr uint64_t begin=image+0x96ce0;
    constexpr uint64_t end=image+0x96f17;
    constexpr uint64_t table=image+0xf9f360;
    const std::array<uint64_t,5> targets = {
      image+0x96d07,image+0x96d42,image+0x96d7a,image+0x96f09,image+0x96db2
    };
    std::vector<jt::Ins> ins;
    // 0x96cec mov eax, edi
    auto mov=op(image+0x96cec,2,jt::K::Mov);
    mov.dst.k=jt::Op::Reg; mov.dst.reg=0;
    mov.src.k=jt::Op::Reg; mov.src.reg=7;
    ins.push_back(mov);
    // 0x96cee cmp edi,4
    auto cmp=op(image+0x96cee,3,jt::K::Cmp);
    cmp.dst.k=jt::Op::Reg; cmp.dst.reg=7;
    cmp.src.k=jt::Op::Imm; cmp.src.imm=4;
    ins.push_back(cmp);
    // 0x96cf1 ja 0x96f09
    auto ja=op(image+0x96cf1,6,jt::K::Jcc);
    ja.cc=7; ja.src.k=jt::Op::Imm;
    ja.src.imm=(int64_t)(image+0x96f09)-(int64_t)(ja.pc+ja.size);
    ins.push_back(ja);
    // 0x96cf7 lea rdx,[rip+0xf08662] -> table in separate .rodata
    auto lea=op(image+0x96cf7,7,jt::K::Lea);
    lea.dst.k=jt::Op::Reg; lea.dst.reg=2;
    lea.src.k=jt::Op::Mem; lea.src.rip=true;
    lea.src.imm=(int64_t)table-(int64_t)(lea.pc+lea.size);
    ins.push_back(lea);
    // 0x96cfe movsxd rax,dword ptr [rdx+rax*4]
    auto load=op(image+0x96cfe,4,jt::K::Movsxd);
    load.dst.k=jt::Op::Reg;load.dst.reg=0;
    load.src.k=jt::Op::Mem;load.src.base=2;load.src.index=0;load.src.scale=4;
    ins.push_back(load);
    auto add=op(image+0x96d02,3,jt::K::Add);
    add.dst.k=jt::Op::Reg;add.dst.reg=0;
    add.src.k=jt::Op::Reg;add.src.reg=2;
    ins.push_back(add);
    auto jump=op(image+0x96d05,2,jt::K::JmpInd);
    jump.src.k=jt::Op::Reg;jump.src.reg=0;
    ins.push_back(jump);

    jt::Env env{begin,end,[&](uint64_t address,int32_t& out) {
        if (address<table || address>=table+4*targets.size() ||
            (address-table)%4) return false;
        const size_t index=(address-table)/4;
        out=(int32_t)((int64_t)targets[index]-(int64_t)table);
        return true;
    }};
    const auto js=jt::analyze(ins,env);
    if (js.size()!=1 || js[0].why!=jt::Why::Resolved ||
        js[0].entries!=5 || js[0].targets.size()!=5) {
        std::fprintf(stderr,"FAILED: expected 5 switch targets outside owning function, got %zu entries, reason=%s\\n",
                     js.empty()?0:js[0].targets.size(),js.empty()?"empty":jt::whyName(js[0].why));
        return 1;
    }
    std::vector<uint64_t> expected(targets.begin(),targets.end());
    std::sort(expected.begin(),expected.end());
    if(js[0].targets!=expected) return 2;
    std::puts("PASS: all 5 .rodata jump targets resolved without per-game exceptions");
    return 0;
}
