#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Adapt SotC's x86-only SRT walker to the existing Daedalus ARM64 IR pass.

Only modifies the *staged SotC renderer*. Its original PC implementation and
the standalone God of War III renderer stay unchanged.

The SotC version uses a four-argument walker, dynamic-indexed 512-dword SRT
windows and a serialized walker cache. The Android port therefore needs all
three adaptations, not just an ARM64 replacement for UNREACHABLE().
"""
from pathlib import Path
import shutil


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"SotC SRT staging: {label} expected once; saw {count}")
    return text.replace(old, new)


def patch_sotc_arm64(root: Path, staged_gpu: Path) -> None:
    root = root.resolve()
    staged_gpu = staged_gpu.resolve()
    src = staged_gpu / "shadps4/shader_recompiler/ir/passes"
    dest_pass = src / "flatten_extended_userdata_pass.cpp"
    original = dest_pass.read_text()
    assert "FlattenExtendedUserdataPass unimplemented for target architecture." in original
    assert "CopyFlatbufPlacement" in original
    assert "ReadConstDynamicWindowFlag" in original

    source = (root / "gpu/shadps4/shader_recompiler/ir/passes/"
              "flatten_extended_userdata_pass.cpp").read_text()
    # Keep the tested portable SRT IR lowering from Daedalus GoW3. We use
    # SotC's GPU memory copier for guest page reads and the original SotC
    # shader-cache ABI rather than GoW3's raw pointer reader.
    source = replace_once(source, '#include "../../../../../src/runtime.h"\n', "",
                          "remove GoW3 runtime dependency")
    source = replace_once(source, '#include "shader_recompiler/ir/passes/srt_arm64.h"',
                          '#include "shader_recompiler/ir/passes/srt_sotc_portable.h"',
                          "SotC portable bytecode")
    source = replace_once(source, '#include <queue>',
                          '#include <queue>\n#include <optional>\n#include <ranges>\n#include "core/memory.h"',
                          "cross-platform shader pass headers")

    start_marker = "#else\n\nnamespace {\nusing namespace Shader::Arm64Srt;\n} // namespace\n\nnamespace Shader {\n"
    end_marker = "#endif\n\nnamespace {\nusing namespace Shader;\n"
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    portable = r'''#else

namespace {
using namespace Shader::SotcArm64Srt;
}

namespace Shader {

struct SrtProgram {
    std::vector<u32> words;
};

void SrtCopyWindow(u32* dst, u64 src, u64 bytes) {
    Core::Memory::Instance()->CopySparseMemory(src, reinterpret_cast<u8*>(dst), bytes);
}

const SrtWalkerContext* GetSrtWalkerContext() {
    static const SrtWalkerContext context{};
    return &context;
}
void SetSrtCleanLoad(bool (*)(u64, u32, u64*)) {}
void MarkSrtCleanPages(u64, u32) {}
void SetSrtReadProtectedPages(u64, u64, bool) {}
bool IsSrtWalkerCode(const void*) { return false; } // no native ARM64 JIT; safe interpreter

void RunSrtWalker(SrtProgram* program, const u32* user_data, u32* flat,
                  PFN_SrtCopyWindow copy, const SrtWalkerContext* context) {
    (void)context;
    if (!program || !SotcArm64Srt::Run(program->words, user_data, flat, copy)) {
        static std::atomic<u32> errors{0};
        if (errors.fetch_add(1, std::memory_order_relaxed) < 4)
            LOG_ERROR(Render_Recompiler, "SotC ARM64 SRT bytecode validation/execution failed");
    }
}

const void* SrtWalkerCode(PFN_SrtWalker walker) {
    return walker.program ? walker.program->words.data() : nullptr;
}

PFN_SrtWalker RegisterWalkerCode(const u8* ptr, size_t size) {
    if (!ptr || size % sizeof(u32) || size > SotcArm64Srt::MaxWords * sizeof(u32))
        return {};
    auto program = std::make_unique<SrtProgram>();
    program->words.resize(size / sizeof(u32));
    std::memcpy(program->words.data(), ptr, size);
    if (!SotcArm64Srt::Validate(program->words))
        return {}; // refuse stale x86 walker bytes from older shader caches
    static std::mutex mutex;
    static std::vector<std::unique_ptr<SrtProgram>> programs;
    std::scoped_lock lock{mutex};
    auto* result = program.get();
    programs.push_back(std::move(program));
    return SrtWalker{result};
}

} // namespace Shader

'''
    source = source[:start] + portable + source[end:]

    # Restore SotC's dynamic 512-dword SRT window semantics. A dynamic IR
    # index cannot be evaluated by the CPU walker; a shader executes it.
    source = replace_once(source,
        '''static inline void SetFlatbufOffset(IR::Inst* inst, u16 offset) {''',
        '''static inline void CopyFlatbufPlacement(IR::Inst* dst, const IR::Inst* src) {
    if (src->GetOpcode() == IR::Opcode::ReadConst) {
        dst->SetFlags(src->Flags<u32>());
        return;
    }
    auto info = dst->Flags<IR::BufferInstInfo>();
    info.flatbuf_off_dw.Assign(GetFlatbufOffset(src));
    dst->SetFlags(info);
}

static inline void SetFlatbufOffset(IR::Inst* inst, u16 offset) {''',
        "restore dynamic-window duplicate placement")
    source = replace_once(source,
        '''    SrtProgram program{SrtMagic};''',
        '''    SrtProgram program{SrtMagic, 0};''',
        "ARM64 bytecode format with flattened-buffer size")
    source = replace_once(source,
        '''    program.push_back(OpEnd);
    const size_t size = program.size() * sizeof(u32);''',
        '''    program.push_back(OpEnd);
    program[1] = pass_info.dst_off_dw;
    const size_t size = program.size() * sizeof(u32);''',
        "ARM64 bytecode header and bounds")

    before = '''    auto* use_list = pass_info.GetUsesAsPointer(subtree);
    ASSERT(use_list);
    for (auto [src_off_dw, use] : *use_list) {
        if (src_off_dw.IsImmediate()) {
            p.insert(p.end(), {OpCopyImm, src_off_dw.U32(), pass_info.dst_off_dw});
        } else {
            SrtProgram offset;
            if (!ComputeOffset(offset, pass_info, src_off_dw)) {
                LOG_ERROR(Render_Recompiler, "Failed to compute offset for SRT walker");
                continue;
            }
            p.insert(p.end(), offset.begin(), offset.end());
            p.insert(p.end(), {OpCopyDyn, pass_info.dst_off_dw});
        }
        SetFlatbufOffset(use, pass_info.dst_off_dw++);
    }'''
    after = '''    auto* use_list = pass_info.GetUsesAsPointer(subtree);
    ASSERT(use_list);
    std::optional<u32> dynamic_window;
    for (auto [src_off_dw, use] : *use_list) {
        if (src_off_dw.IsImmediate()) {
            p.insert(p.end(), {OpCopyImm, src_off_dw.U32(), pass_info.dst_off_dw});
        } else {
            SrtProgram offset;
            if (!ComputeOffset(offset, pass_info, src_off_dw)) {
                if (use->GetOpcode() != IR::Opcode::ReadConst) {
                    LOG_ERROR(Render_Recompiler, "Cannot translate SotC SRT dynamic index");
                    continue;
                }
                // The offset belongs to a shader runtime loop. Copy the
                // window and let the shader evaluate the dynamic index.
                if (!dynamic_window) {
                    dynamic_window = pass_info.dst_off_dw;
                    ASSERT(pass_info.dst_off_dw <= 65535 - ReadConstDynamicWindowDwords);
                    p.insert(p.end(), {OpCopyWindow, pass_info.dst_off_dw});
                    pass_info.dst_off_dw += ReadConstDynamicWindowDwords;
                }
                use->SetFlags(*dynamic_window | ReadConstDynamicWindowFlag);
                continue;
            }
            p.insert(p.end(), offset.begin(), offset.end());
            p.insert(p.end(), {OpCopyDyn, pass_info.dst_off_dw});
        }
        SetFlatbufOffset(use, pass_info.dst_off_dw++);
    }'''
    source = replace_once(source,before,after,"preserve dynamic SRT windows")
    source = replace_once(source,
        '''        SetFlatbufOffset(readconst, GetFlatbufOffset(original));''',
        '''        CopyFlatbufPlacement(readconst, original);''',
        "copy dynamic flags for deduplicated ReadConst")

    # This source is only compiled on Android; we preserve the PC source
    # in the original upstream tree for ongoing parity audits.
    if ("SotcArm64Srt::Run" not in source or
            "FlattenExtendedUserdataPass unimplemented for target architecture." in source):
        raise ValueError("Android SRT still has unreachable code")
    dest_pass.write_text(source)
    shutil.copy2(root / "ports/sotc/android/srt_sotc_portable.h",
                 src / "srt_sotc_portable.h")

    header = src / "srt.h"
    text = header.read_text()
    text = replace_once(text, '#include "common/types.h"',
                        '#include "common/types.h"\n#include "common/arch.h"',
                        "SRT platform header")
    old = '''using PFN_SrtWalker = void PS4_SYSV_ABI (*)(const u32* /*user_data*/, u32* /*flat_dst*/,
                                            PFN_SrtCopyWindow /*copy_window*/,
                                            const SrtWalkerContext* /*context*/);'''
    new = '''#ifdef ARCH_ARM64
struct SrtProgram;
void RunSrtWalker(SrtProgram* program, const u32* user_data, u32* flat_dst,
                  PFN_SrtCopyWindow copy_window, const SrtWalkerContext* context);
struct SrtWalker {
    SrtProgram* program{};
    explicit operator bool() const { return program != nullptr; }
    void operator()(const u32* user_data, u32* flat_dst, PFN_SrtCopyWindow copy_window,
                    const SrtWalkerContext* context) const {
        if (program) RunSrtWalker(program, user_data, flat_dst, copy_window, context);
    }
};
using PFN_SrtWalker = SrtWalker;
static_assert(sizeof(PFN_SrtWalker) == sizeof(void*),
              "SotC pipeline cache requires a pointer-sized walker");
const void* SrtWalkerCode(PFN_SrtWalker walker);
#else
using PFN_SrtWalker = void PS4_SYSV_ABI (*)(const u32* /*user_data*/, u32* /*flat_dst*/,
                                            PFN_SrtCopyWindow /*copy_window*/,
                                            const SrtWalkerContext* /*context*/);
#endif'''
    text = replace_once(text,old,new,"ARM64 SRT walker ABI")
    header.write_text(text)
    serialized = (staged_gpu /
        "shadps4/video_core/renderer_vulkan/vk_pipeline_serialization.cpp")
    text = serialized.read_text()
    text = replace_once(text,'''        srt.Write(reinterpret_cast<void*>(walker_func), walker_func_size);''',
        '''#ifdef ARCH_ARM64
        srt.Write(SrtWalkerCode(walker_func), walker_func_size);
#else
        srt.Write(reinterpret_cast<void*>(walker_func), walker_func_size);
#endif''',
        "serialize ARM64 portable bytecode rather than an invalid function pointer")
    serialized.write_text(text)


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--gpu", type=Path, required=True)
    a=p.parse_args()
    patch_sotc_arm64(a.root,a.gpu)
    print("SotC ARM64 SRT bytecode, dynamic-window semantics and cache ABI staged")
