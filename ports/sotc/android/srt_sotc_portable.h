// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
// Android/ARM64 SRT walker bytecode. A safe interpreter first: there is no
// attempt to execute the x86-64 Xbyak walker in an AArch64 process.
#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <span>

namespace Shader::SotcArm64Srt {
enum Op : std::uint32_t {
    End, PushImm, PushDyn, Pop, CopyImm, CopyDyn, UserData, Flat, Imm,
    Add, Sub, Mul, Shl, Shr, And, Or, Xor, Not, UMin, UMax, BitExtract,
    CopyWindow,
};
// Keep the emitter's proven GoW3 IR lowering API; Android uses a different
// bytecode interpreter while preserving its SrtOp parameter type.
using SrtOp=Op;
constexpr std::uint32_t Magic=0x33545253u; // SRT3: not x86 walker bytes or GoW3 SRT
constexpr std::uint32_t MaxDepth=64, MaxValues=32;
constexpr std::uint32_t MaxWords=262144, WindowDwords=512;
constexpr std::uint32_t MaxFlatDwords=65535;

inline bool Validate(std::span<const std::uint32_t> words) {
    if (words.size()<3 || words.size()>MaxWords || words[0]!=Magic ||
        words[1]<16 || words[1]>MaxFlatDwords) return false;
    const std::uint32_t flat_size=words[1];
    std::size_t pc=2;
    unsigned depth=0, values=0;
    const auto next=[&](std::uint32_t& out) {
        if (pc>=words.size()) return false;
        out=words[pc++]; return true;
    };
    while (pc<words.size()) {
        std::uint32_t op=words[pc++], arg=0;
        switch (op) {
        case End: return depth==0 && values==0 && pc==words.size();
        case PushImm:
            if (++depth>MaxDepth || !next(arg)) return false;
            break;
        case PushDyn:
            if (++depth>MaxDepth || !values) return false;
            --values;
            break;
        case Pop:
            if (!depth) return false;
            --depth;
            break;
        case CopyImm:
            if (!next(arg) || !next(arg) || arg>=flat_size) return false;
            break;
        case CopyDyn:
            if (!values || !next(arg) || arg>=flat_size) return false;
            --values;
            break;
        case CopyWindow:
            if (!next(arg) || arg>flat_size ||
                WindowDwords>flat_size-arg) return false;
            break;
        case UserData:
            if (!next(arg) || arg>=16 || ++values>MaxValues) return false;
            break;
        case Flat:
            if (!next(arg) || arg>=flat_size || ++values>MaxValues) return false;
            break;
        case Imm:
            if (!next(arg) || ++values>MaxValues) return false;
            break;
        case Not:
            if (!values) return false;
            break;
        case BitExtract:
            if (values<3) return false;
            values-=2;
            break;
        case Add: case Sub: case Mul: case Shl: case Shr:
        case And: case Or: case Xor: case UMin: case UMax:
            if (values<2) return false;
            --values;
            break;
        default: return false;
        }
    }
    return false;
}

using Copy = void (*)(std::uint32_t*, std::uint64_t, std::uint64_t);

// The copy callback is the SotC GPU's sparse/backing-memory copy service:
// it returns zero for unmapped or protected guest pages, rather than
// dereferencing arbitrary guest pointers from the host Vulkan thread.
inline bool Run(std::span<const std::uint32_t> words,
                const std::uint32_t* user_data, std::uint32_t* flat, Copy copy) {
    // All bytecode is validated exactly once by RegisterWalkerCode before
    // cache insertion. Do not re-parse it on every Vulkan draw call.
    if (!copy || !user_data || !flat || words.size()<3 || words[0]!=Magic) return false;
    std::array<std::uint64_t, MaxDepth> stack{};
    std::array<std::uint32_t, MaxValues> values{};
    std::uint64_t pointer=reinterpret_cast<std::uintptr_t>(user_data);
    unsigned depth=0,count=0;
    std::size_t pc=2;
    for (;;) {
        const std::uint32_t op=words[pc++];
        std::uint32_t arg=0;
        switch(op) {
        case End: return true;
        case PushImm: case PushDyn: {
            const std::uint32_t dw=op==PushImm ? words[pc++] : values[--count];
            std::uint32_t data[2]{};
            if (pointer==reinterpret_cast<std::uintptr_t>(user_data)) {
                // First SRT root is the host-owned 16-dword user-data array,
                // not a guest allocation tracked by Core::Memory.
                if (dw+1<16) std::memcpy(data,user_data+dw,sizeof(data));
            } else {
                copy(data,pointer+(std::uint64_t(dw)<<2),sizeof(data));
            }
            stack[depth++]=pointer;
            pointer=(std::uint64_t(data[0]) | (std::uint64_t(data[1])<<32)) &
                     UINT64_C(0xFFFFFFFFFFFF);
            break;
        }
        case Pop: pointer=stack[--depth]; break;
        case CopyImm: case CopyDyn: {
            const std::uint32_t dw=op==CopyImm ? words[pc++] : values[--count];
            const std::uint32_t dst=words[pc++];
            if (pointer==reinterpret_cast<std::uintptr_t>(user_data)) {
                if (dw<16) flat[dst]=user_data[dw];
                else flat[dst]=0;
            } else {
                copy(&flat[dst],pointer+(std::uint64_t(dw)<<2),sizeof(std::uint32_t));
            }
            break;
        }
        case CopyWindow:
            arg=words[pc++];
            copy(flat+arg,pointer,std::uint64_t(WindowDwords)*sizeof(std::uint32_t));
            break;
        case UserData:
            arg=words[pc++]; values[count++]=user_data[arg]; break;
        case Flat:
            arg=words[pc++]; values[count++]=flat[arg]; break;
        case Imm:
            arg=words[pc++]; values[count++]=arg; break;
        case Not: values[count-1]=~values[count-1]; break;
        case BitExtract: {
            const std::uint32_t bits=values[--count], shift=values[--count]&31;
            const std::uint32_t mask=bits>=32 ? UINT32_MAX :
                                     bits==0 ? 0u : ((std::uint32_t(1)<<bits)-1u);
            values[count-1]=(values[count-1]>>shift)&mask;
            break;
        }
        default: {
            const std::uint32_t b=values[--count];
            std::uint32_t& a=values[count-1];
            switch(op) {
            case Add:a+=b;break;
            case Sub:a-=b;break;
            case Mul:a*=b;break;
            case Shl:a<<=(b&31);break;
            case Shr:a>>=(b&31);break;
            case And:a&=b;break;
            case Or:a|=b;break;
            case Xor:a^=b;break;
            case UMin:a=std::min(a,b);break;
            case UMax:a=std::max(a,b);break;
            default:return false;
            }
        }
        }
    }
}

// Bytecode emitter names from the existing Daedalus ARM64 SRT generator.
inline constexpr Op OpEnd=End, OpPushImm=PushImm, OpPushDyn=PushDyn, OpPop=Pop;
inline constexpr Op OpCopyImm=CopyImm, OpCopyDyn=CopyDyn, OpUserData=UserData;
inline constexpr Op OpFlat=Flat, OpImm=Imm, OpAdd=Add, OpSub=Sub, OpMul=Mul;
inline constexpr Op OpShl=Shl, OpShr=Shr, OpAnd=And, OpOr=Or, OpXor=Xor;
inline constexpr Op OpNot=Not, OpUMin=UMin, OpUMax=UMax;
inline constexpr Op OpBitFieldUExtract=BitExtract, OpCopyWindow=CopyWindow;
inline constexpr std::uint32_t SrtMagic=Magic;
} // namespace Shader::SotcArm64Srt
