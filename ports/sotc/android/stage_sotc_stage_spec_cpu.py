#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""SotC Android CPU fast path for the observed ~43ms CP / ~35ms draw threads.

No guessed spin counts or register granularity: the 0.1.28 changes are NOT
present. Reuse an already compiled fragment/compute shader permutation ONLY
after verifying that its complete flattened SRT/user data, program base,
runtime specialization data, binding base and module count are bit-for-bit
unchanged. Vertex, fetch-shader and tessellation paths (which read additional
guest memory) always use the original code. Every draw continues to refresh
the SRT and uses its own dynamic descriptor/user data; no caching of actual
guest texture/buffer bindings, no shader/draw skipping.

Remove one full dynamic shader-buffer copy on the draw thread: transfer each
per-draw flattened SRT snapshot by swapping std::vector storage. The ring
slot cannot be reused by CP before the draw operation has finished; both
objects retain their own storage for the next draw. The incoming snapshot
and guest-memory readback safety are unchanged.

Both fast paths have explicit runtime opt-outs, default ON only in ARM64.
"""
from pathlib import Path

def exact(src: str, original: str, changed: str, label: str, count: int=1) -> str:
    actual=src.count(original)
    if actual != count:
        raise ValueError(f"SotC 029 source drift: {label}: {actual} instead of {count}")
    return src.replace(original, changed)

def patch_sotc_stage_spec_cpu(gpu: Path) -> None:
    gpu=Path(gpu)
    liverpool=gpu/'shadps4/video_core/amdgpu/liverpool.cpp'
    s=liverpool.read_text()
    old='        rt.flattened_ud_buf.assign(stage.flat.begin(), stage.flat.end());'
    new='''        // SotC Android: the consumer owns this ring slot until ExecuteBackOp
        // returns and back_tail is published. Exchange the complete immutable
        // per-draw SRT storage instead of copying it a second time.
#if defined(__aarch64__)
        static const bool snapshot_swap = [] {
            const char* v = std::getenv("SOTC_STAGE_SNAPSHOT_SWAP");
            return !v || v[0] != '0';
        }();
        if (snapshot_swap) {
            rt.flattened_ud_buf.swap(stage.flat);
        } else
#endif
        {
            rt.flattened_ud_buf.assign(stage.flat.begin(), stage.flat.end());
        }'''
    s=exact(s,old,new,"draw-thread second flattened-SRT copy")
    for must in ('std::memcpy(&back_regs.reg_array[', 'back_tail.store(tail, std::memory_order_seq_cst)',
                 'stage.flat.assign(rt.flattened_ud_buf.begin(), rt.flattened_ud_buf.end())'):
        if must not in s:
            raise ValueError(f"SotC 029 stage snapshot/order invariant changed: {must}")
    liverpool.write_text(s)

    header=gpu/'shadps4/video_core/renderer_vulkan/vk_pipeline_cache.h'
    s=header.read_text()
    old='''    Shader::Info info;
    ModuleList modules{};
    /// sotc: permutations being translated by a pipeline worker'''
    new='''    Shader::Info info;
    ModuleList modules{};
    // SotC ARM64: CP-side last *verified* shader permutation. This memo
    // stores a type-specialization key, NOT any guest resources or GPU state.
    // Store the entire flattened SRT data; partial hashes are insufficient.
    struct LastSafeSpecialization {
        std::vector<u32> flat;
        Shader::RuntimeInfo runtime_info{};
        Shader::Backend::Bindings start{};
        VAddr program_base{};
        size_t perm{};
        size_t module_count{};
        bool valid{};
    } sotc_last_safe_spec{};
    /// sotc: permutations being translated by a pipeline worker'''
    s=exact(s,old,new,"per-program exact specialization cache")
    header.write_text(s)

    cache=gpu/'shadps4/video_core/renderer_vulkan/vk_pipeline_cache.cpp'
    s=cache.read_text()
    old='''    info.PgmBase() = params.Base(); // Needs to be actualized for inline cbuffer address fixup
    info.UserData() = params.user_data;
    info.RefreshFlatBuf();
    auto spec = Shader::StageSpecialization(info, rt, profile, binding);'''
    new='''    info.PgmBase() = params.Base(); // Needs to be actualized for inline cbuffer address fixup
    info.UserData() = params.user_data;
    // Always refresh from real guest memory before memo lookup: CPU writes,
    // GPU readbacks, aliasing sharp tables and SRT walker inputs remain live.
    info.RefreshFlatBuf();
    const auto sotc_start_bindings = binding;
#if defined(__aarch64__)
    static const bool sotc_stage_spec_memo = [] {
        const char* v = std::getenv("SOTC_STAGE_SPEC_MEMO");
        return !v || v[0] != '0';
    }();
    // Only FS/CS: vertex fetch shaders and tessellation specializations can
    // read *additional* guest memory not represented in FlatBuf.
    const bool sotc_memo_eligible = sotc_stage_spec_memo &&
        !EmulatorSettings.IsShaderCollect() &&
        (sw_stage == SwStage::Fragment || sw_stage == SwStage::Compute) &&
        !program->translate_in_place && program->pending_specs.empty();
    auto& sotc_last = program->sotc_last_safe_spec;
    if (sotc_memo_eligible) {
        if (SotcStats::kFpsLog) {
            SotcStats::stage_spec_lookups.fetch_add(1, std::memory_order_relaxed);
        }
        if (sotc_last.valid &&
            sotc_last.module_count == program->modules.size() &&
            sotc_last.perm < program->modules.size() &&
            sotc_last.program_base == info.PgmBase() &&
            sotc_last.start == binding &&
            sotc_last.runtime_info == rt &&
            sotc_last.flat == info.FlatBuf()) {
            // The old find() path calls AddBindings too. Do not reuse dynamic
            // descriptor writes or per-draw SRT data; only the module variant.
            const size_t matched_idx = sotc_last.perm;
            info.AddBindings(binding);
            const auto& matched = program->modules[matched_idx];
            if (SotcStats::kFpsLog) {
                SotcStats::stage_spec_hits.fetch_add(1, std::memory_order_relaxed);
            }
            return std::make_tuple(&info, matched.module,
                                   HashCombine(params.hash, matched_idx));
        }
    }
#endif
    auto spec = Shader::StageSpecialization(info, rt, profile, binding);'''
    s=exact(s,old,new,"real guest SRT refresh and exact CP shader specialization cache")

    # Record only a validated/synchronous permutation, never a pending job.
    # In this original flow modules are stable until Add/InsertPermut; module
    # count protects against later worker installation.
    old='''    if (auto& fetch = program->modules[perm_idx].spec.fetch_shader_data; !fetch.Empty()) {
        fetch_shader = &fetch;
    }
    return std::make_tuple(&program->info, module, perm_hash);
}'''
    new='''#if defined(__aarch64__)
    if (sotc_memo_eligible && perm_idx < program->modules.size()) {
        // Store the actual fully-refreshed guest SRT, runtime specialization,
        // binding base and program address; never assume shader tables unchanged.
        auto& last = program->sotc_last_safe_spec;
        last.flat.assign(info.FlatBuf().begin(), info.FlatBuf().end());
        last.runtime_info = rt;
        last.start = sotc_start_bindings;
        last.program_base = info.PgmBase();
        last.perm = perm_idx;
        last.module_count = program->modules.size();
        last.valid = true;
    } else {
        program->sotc_last_safe_spec.valid = false;
    }
#endif
    if (auto& fetch = program->modules[perm_idx].spec.fetch_shader_data; !fetch.Empty()) {
        fetch_shader = &fetch;
    }
    return std::make_tuple(&program->info, module, perm_hash);
}'''
    s=exact(s,old,new,"update cache only after existing module is resolved")
    cache.write_text(s)

    stats=gpu/'shadps4/video_core/sotc_stats.h'
    s=stats.read_text()
    old='inline const bool kCmdStats = std::getenv("SOTC_CMD_STATS") != nullptr;'
    new='''inline const bool kCmdStats = std::getenv("SOTC_CMD_STATS") != nullptr;
/// SotC ARM64: FS/CS shader-specialization memo hit rate, counted only when
/// SOTC_FPS=1 for the controlled A/B diagnosis.
inline std::atomic<uint64_t> stage_spec_lookups{0};
inline std::atomic<uint64_t> stage_spec_hits{0};'''
    s=exact(s,old,new,"optional shader specialization hit metrics")
    stats.write_text(s)

    # The profile already prints FPS every five seconds. Report hit rate on
    # the same thread at that cadence, not per draw.
    driver=gpu/'shadps4/core/libraries/videoout/driver.cpp'
    s=driver.read_text()
    old='''            if (SotcStats::kDrawSplit && split_frames && split_tick0) {'''
    new='''            if (const auto lookups =
                    SotcStats::stage_spec_lookups.exchange(0, std::memory_order_relaxed)) {
                const auto hits =
                    SotcStats::stage_spec_hits.exchange(0, std::memory_order_relaxed);
                std::fprintf(stderr, "SOTC STAGE SPEC MEMO hits %llu/%llu (%.1f%%)\\n",
                             static_cast<unsigned long long>(hits),
                             static_cast<unsigned long long>(lookups),
                             100.0 * double(hits) / double(lookups));
            }
            if (SotcStats::kDrawSplit && split_frames && split_tick0) {'''
    s=exact(s,old,new,"five-second memo effectiveness counter")
    driver.write_text(s)
    print("SotC ARM64 CP: exact FS/CS specialization reuse after live SRT refresh; "
          "draw: zero-copy stage vector swap; 64-dword registers/4096 spins unchanged.")


if __name__ == "__main__":
    import argparse
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--gpu',type=Path,required=True)
    patch_sotc_stage_spec_cpu(ap.parse_args().gpu)
