#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Android SotC 0.1.53: adapt the measured forest shader prefetch from PC 53fd029.

Prefetch is exact-program matching and only touches the staged SotC renderer.
No readback, shader output, presentation, guest game data, or graphics draw
behavior is changed. Unknown packet types are not guessed.
"""
from pathlib import Path

LIVERPOOL_PREFETCH = "static bool ComputePrefetchEnabled() {\n    static const bool enabled = [] {\n        const char* v = std::getenv(\"SOTC_COMPUTE_PREFETCH\");\n        return !v || v[0] != '0';\n    }();\n    return enabled;\n}\n\nvoid Liverpool::PrefetchComputeShaders(std::span<const u32> cb, ComputeProgram& cs, int depth) {\n    // Only the compute registers are followed (a copy: the real state is untouched); anything\n    // the walk does not understand ends it. A wrong guess costs a wasted translation at worst:\n    // the dispatch checks the worker's result against its own state.\n    while (!cb.empty()) {\n        const auto* header = reinterpret_cast<const PM4Header*>(cb.data());\n        if (header->type == 2) {\n            cb = cb.subspan(1);\n            continue;\n        }\n        if (header->type != 3) {\n            return;\n        }\n        const u32 count = header->type3.NumWords();\n        if (count + 1 > cb.size()) {\n            return;\n        }\n        switch (header->type3.opcode) {\n        case PM4ItOpcode::SetShReg: {\n            const auto* set_data = reinterpret_cast<const PM4CmdSetData*>(header);\n            const u32 words = count - 1;\n            if (count >= 1 && set_data->reg_offset >= 0x200 &&\n                set_data->reg_offset - 0x200 + words <= sizeof(ComputeProgram) / 4) {\n                std::memcpy(reinterpret_cast<u32*>(&cs) + (set_data->reg_offset - 0x200),\n                            header + 2, words * sizeof(u32));\n            }\n            break;\n        }\n        case PM4ItOpcode::DispatchDirect: {\n            const auto* dispatch = reinterpret_cast<const PM4CmdDispatchDirect*>(header);\n            cs.dispatch_initiator = dispatch->dispatch_initiator; // as the real one sets it\n            if (dispatch->dispatch_initiator & 1) {\n                rasterizer->PrefetchComputeShader(cs);\n            }\n            break;\n        }\n        case PM4ItOpcode::DispatchIndirect:\n            if (cs.dispatch_initiator & 1) {\n                rasterizer->PrefetchComputeShader(cs);\n            }\n            break;\n        case PM4ItOpcode::IndirectBuffer: {\n            const auto* ib = reinterpret_cast<const PM4CmdIndirectBuffer*>(header);\n            if (depth < 4 && ib->Address<const u32>() && ib->ib_size != 0) {\n                PrefetchComputeShaders({ib->Address<const u32>(), ib->ib_size}, cs, depth + 1);\n            }\n            break;\n        }\n        default:\n            break;\n        }\n        cb = cb.subspan(count + 1);\n    }\n}\n"
PIPELINE_PREFETCH = "void PipelineCache::PrefetchCompute(const AmdGpu::ComputeProgram& cs) {\n    if (async_workers.empty() || EmulatorSettings.IsShaderCollect()) {\n        return;\n    }\n    const VAddr address = cs.Address<VAddr>();\n    if (address == 0) {\n        return;\n    }\n    const u8* backing = Core::Memory::Instance()->GetBackingPointer(address);\n    if (!backing) {\n        return;\n    }\n    u64 head;\n    std::memcpy(&head, backing, sizeof(head));\n    const auto [seen, is_new] = prefetch_seen.try_emplace(address, head);\n    if (!is_new) {\n        if (seen->second == head) {\n            return;\n        }\n        seen->second = head;\n    }\n    const auto params = AmdGpu::GetParams(cs);\n    if (params.code.empty() || program_cache.contains(params.hash) ||\n        pending_programs.contains(params.hash) || in_place_programs.contains(params.hash)) {\n        return;\n    }\n    // The runtime info of the dispatch further on, from the walk's registers. The command\n    // processor's own copy of the compute slot is put back (a dispatch may be being bound).\n    auto& slot = runtime_infos[static_cast<u32>(SwStage::Compute)];\n    const Shader::RuntimeInfo saved = slot;\n    cs_override = &cs;\n    const Shader::RuntimeInfo rt = BuildRuntimeInfo(HwStage::Compute, SwStage::Compute);\n    cs_override = nullptr;\n    slot = saved;\n    pending_programs.insert(params.hash);\n    prefetched_computes.insert(params.hash);\n    QueueAsyncTranslate(HwStage::Compute, SwStage::Compute, params, rt, Shader::Backend::Bindings{},\n                        nullptr, nullptr, 0);\n    SotcStats::prefetch_queued.fetch_add(1, std::memory_order_relaxed);\n}\n\nvoid PipelineCache::WaitPrefetchedCompute(u64 hash) {\n    prefetched_computes.erase(hash);\n    if (async_done_count.load(std::memory_order_acquire) != 0) {\n        CollectAsyncPipelines();\n        last_graphics_pipeline = nullptr; // sotc: as after any change of graphics_pipelines\n    }\n    if (!pending_programs.contains(hash)) {\n        SotcStats::prefetch_ready.fetch_add(1, std::memory_order_relaxed);\n        return;\n    }\n    // Counted as shader time of the frame, as the translation it replaces.\n    const SotcStats::FrameTimer frame_timer{SotcStats::FrameCompile};\n    const auto start = std::chrono::steady_clock::now();\n    for (;;) {\n        {\n            std::unique_lock lock{async_mutex};\n            const auto queued = std::ranges::find_if(async_queue, [hash](const auto& job) {\n                return job->translate && !job->translate->program && job->translate->hash == hash;\n            });\n            if (queued != async_queue.end()) {\n                // No worker has started it: translating it here is faster than waiting for\n                // the jobs in front of it.\n                async_queue.erase(queued);\n                --async_translate_queued;\n                lock.unlock();\n                pending_programs.erase(hash);\n                SotcStats::prefetch_taken_back.fetch_add(1, std::memory_order_relaxed);\n                return;\n            }\n            // Running on a worker: wait until it (or another job) is done. Bounded, so a job\n            // dropped by stopping workers cannot hold the command processor.\n            async_done_cv.wait_for(lock, std::chrono::milliseconds(50), [this] {\n                return async_done_count.load(std::memory_order_relaxed) != 0;\n            });\n        }\n        if (async_done_count.load(std::memory_order_acquire) != 0) {\n            CollectAsyncPipelines();\n            last_graphics_pipeline = nullptr;\n        }\n        if (!pending_programs.contains(hash)) {\n            break;\n        }\n        if (std::chrono::steady_clock::now() - start > std::chrono::seconds(2)) {\n            // The worker's result, when it comes, finds the program built and is dropped.\n            pending_programs.erase(hash);\n            break;\n        }\n    }\n    SotcStats::prefetch_waited.fetch_add(1, std::memory_order_relaxed);\n    SotcStats::prefetch_wait_ns.fetch_add(\n        std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() -\n                                                             start)\n            .count(),\n        std::memory_order_relaxed);\n}\n"
RASTER_PREFETCH = "void Rasterizer::PrefetchComputeShader(const AmdGpu::ComputeProgram& cs) {\n    pipeline_cache.PrefetchCompute(cs);\n}\n"

def swap(src: str, old: str, new: str, name: str) -> str:
    n=src.count(old)
    if n!=1:
        raise ValueError(f"SotC forest prefetch {name}: source drift ({n})")
    return src.replace(old,new,1)

def patch_prefetch(gpu: Path) -> None:
    root=gpu/"shadps4/video_core"
    lh=root/"amdgpu/liverpool.h"
    h=lh.read_text()
    h=swap(h,
        "    Task ProcessGraphics(std::span<const u32> dcb, std::span<const u32> ccb);",
        "    Task ProcessGraphics(std::span<const u32> dcb, std::span<const u32> ccb, bool nested = false);\n"
        "    void PrefetchComputeShaders(std::span<const u32> cb, ComputeProgram& cs, int depth);",
        "liverpool API")
    lh.write_text(h)

    lc=root/"amdgpu/liverpool.cpp"
    cpp=lc.read_text()
    before="""Liverpool::Task Liverpool::ProcessGraphics(std::span<const u32> dcb, std::span<const u32> ccb) {
    FIBER_ENTER(dcb_task_name);

    cblock.Reset();"""
    after=LIVERPOOL_PREFETCH+"""Liverpool::Task Liverpool::ProcessGraphics(std::span<const u32> dcb, std::span<const u32> ccb,
                                           bool nested) {
    FIBER_ENTER(dcb_task_name);

    // SotC PC: scan upcoming compute only once per submission, not nested IBs.
    if (!nested && rasterizer && ComputePrefetchEnabled()) {
        ComputeProgram cs = mapped_queues[GfxQueueId].cs_state;
        PrefetchComputeShaders(dcb, cs, 0);
    }

    cblock.Reset();"""
    cpp=swap(cpp,before,after,"graphics prefetch")
    cpp=swap(cpp,
"""                auto task = ProcessGraphics(
                    {indirect_buffer->Address<const u32>(), indirect_buffer->ib_size}, {});""",
"""                auto task = ProcessGraphics(
                    {indirect_buffer->Address<const u32>(), indirect_buffer->ib_size}, {}, true);""",
             "nested IB prefetch")
    cpp=swap(cpp,
"""    FIBER_ENTER(acb_task_name[vqid]);
    auto& queue = asc_queues[{vqid}];

    struct IndirectPatch {""",
"""    FIBER_ENTER(acb_task_name[vqid]);
    auto& queue = asc_queues[{vqid}];

    if constexpr (!is_indirect) {
        if (rasterizer && ComputePrefetchEnabled()) {
            ComputeProgram cs = mapped_queues[vqid + 1].cs_state;
            PrefetchComputeShaders(acb, cs, 0);
        }
    }

    struct IndirectPatch {""", "async compute queue prefetch")
    lc.write_text(cpp)

    ph=root/"renderer_vulkan/vk_pipeline_cache.h"
    h=ph.read_text()
    h=swap(h,"    const ComputePipeline* GetComputePipeline();",
"""    const ComputePipeline* GetComputePipeline();
    void PrefetchCompute(const AmdGpu::ComputeProgram& cs);""", "pipeline public API")
    h=swap(h,"    const Shader::RuntimeInfo& BuildRuntimeInfo(Shader::HwStage stage, Shader::SwStage l_stage);",
"""    const Shader::RuntimeInfo& BuildRuntimeInfo(Shader::HwStage stage, Shader::SwStage l_stage);
    void WaitPrefetchedCompute(u64 hash);""","pipeline worker wait API")
    h=swap(h,
"""    std::unordered_set<u64> in_place_programs; ///< failed on a worker: translated here (CP only)""",
"""    std::unordered_set<u64> in_place_programs; ///< failed on a worker: translated here (CP only)
    // All prefetched programs remain identified by real PS4 shader hash.
    std::unordered_set<u64> prefetched_computes;
    std::unordered_map<u64, u64> prefetch_seen;
    const AmdGpu::ComputeProgram* cs_override{};
    std::condition_variable_any async_done_cv;""","pipeline prefetch fields")
    ph.write_text(h)

    pc=root/"renderer_vulkan/vk_pipeline_cache.cpp"
    cpp=pc.read_text()
    cpp=swap(cpp,'#include "core/emulator_settings.h"',
                   '#include "core/emulator_settings.h"\n#include "core/memory.h"',
                   "GetBackingPointer header")
    cpp=swap(cpp,"    case HwStage::Compute: {\n        const auto& cs_pgm = liverpool->GetCsRegs();",
                 "    case HwStage::Compute: {\n        const auto& cs_pgm = cs_override ? *cs_override : liverpool->GetCsRegs();",
                 "compute registers override")
    cpp=swap(cpp,
"""            RunAsyncTranslate(*job->translate);
            std::scoped_lock lock{async_mutex};
            async_done.push_back(std::move(job));
            async_done_count.fetch_add(1, std::memory_order_release);
            continue;""",
"""            RunAsyncTranslate(*job->translate);
            {
                std::scoped_lock lock{async_mutex};
                async_done.push_back(std::move(job));
                async_done_count.fetch_add(1, std::memory_order_release);
            }
            async_done_cv.notify_all();
            continue;""","worker completion notification")
    cpp=swap(cpp,
       "const ComputePipeline* PipelineCache::GetComputePipeline() {",
       PIPELINE_PREFETCH+"const ComputePipeline* PipelineCache::GetComputePipeline() {",
       "PC prefetch and bounded wait")
    cpp=swap(cpp,
"""    const auto& rt = BuildRuntimeInfo(hw_stage, sw_stage);
    if (async_ok && !program_cache.contains(params.hash) &&""",
"""    const auto& rt = BuildRuntimeInfo(hw_stage, sw_stage);
    if (!async_ok && hw_stage == HwStage::Compute && !prefetched_computes.empty() &&
        prefetched_computes.contains(params.hash)) {
        WaitPrefetchedCompute(params.hash);
    }
    if (async_ok && !program_cache.contains(params.hash) &&""",
             "consume prefetched compute")
    pc.write_text(cpp)

    rh=root/"renderer_vulkan/vk_rasterizer.h"
    h=rh.read_text()
    h=swap(h,"    const Pipeline* LookupComputePipeline();",
         "    const Pipeline* LookupComputePipeline();\n"
         "    void PrefetchComputeShader(const AmdGpu::ComputeProgram& cs);",
         "raster prefetch API")
    rh.write_text(h)
    rc=root/"renderer_vulkan/vk_rasterizer.cpp"
    cpp=rc.read_text()
    cpp=swap(cpp,
"""const Pipeline* Rasterizer::LookupComputePipeline() {
    return pipeline_cache.GetComputePipeline();
}
""",
"""const Pipeline* Rasterizer::LookupComputePipeline() {
    return pipeline_cache.GetComputePipeline();
}

"""+RASTER_PREFETCH,
        "raster handoff")
    rc.write_text(cpp)

    stats=root/"sotc_stats.h"
    s=stats.read_text()
    s=swap(s,
"""inline std::atomic<uint64_t> async_translate_skips{0};""",
"""inline std::atomic<uint64_t> async_translate_skips{0};
inline std::atomic<uint64_t> prefetch_queued{0}, prefetch_ready{0}, prefetch_waited{0},
    prefetch_wait_ns{0}, prefetch_taken_back{0};""", "prefetch stats")
    stats.write_text(s)
    print("SotC forest prefetch: ahead-of-dispatch compute translation with CPU fallback")

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--gpu",type=Path,required=True)
    patch_prefetch(p.parse_args().gpu)
