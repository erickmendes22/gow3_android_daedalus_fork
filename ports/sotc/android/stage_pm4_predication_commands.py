#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Finish the real PM4 predication port for SotC Android command processing.

Requires stage_pm4_predication.patch first. Uses original SotC's own
Liverpool graphics queue and Rasterizer; leaves other ports unchanged.
"""
from pathlib import Path
from stage_pm4_predication import replace_once

def patch(gpu: Path):
    core = gpu / "shadps4/video_core"
    path = core / "amdgpu/pm4_cmds.h"
    s = path.read_text()
    snippet = '''
struct PM4CmdPredExec {
    PM4Type3Header header;
    union {
        u32 control;
        BitField<0, 14, u32> exec_count;
        BitField<24, 8, u32> device_select;
    };
};

enum class PredicationOp : u32 {
    Clear = 0, Zpass = 1, PrimCount = 2, Bool64 = 3, Bool32 = 4,
};

enum class PredicationHint : u32 { Wait = 0, NowaitDraw = 1 };

struct PM4CmdSetPredication {
    PM4Type3Header header;
    u32 start_addr_lo;
    union {
        u32 pred_properties;
        BitField<0, 8, u32> start_addr_hi;
        BitField<8, 1, u32> draw_visible;
        BitField<12, 2, PredicationHint> hint;
        BitField<16, 3, PredicationOp> pred_op;
        BitField<31, 1, u32> continue_predication;
    };
    VAddr Address() const {
        return (u64(start_addr_hi.Value()) << 32) | (u64(start_addr_lo) & 0xfffffff0ULL);
    }
};
'''
    s = replace_once(s, "} // namespace AmdGpu", snippet + "\n} // namespace AmdGpu",
                     "PM4 predicate packet structs")
    path.write_text(s)

    path = core / "amdgpu/liverpool.h"
    s = path.read_text()
    s = replace_once(s,
        '''    void BindRasterizer(Vulkan::Rasterizer* rasterizer_) {
        rasterizer = rasterizer_;
    }''',
        '''    void BindRasterizer(Vulkan::Rasterizer* rasterizer_) {
        rasterizer = rasterizer_;
    }

    bool IsPacketPredicated() const {
        return packet_predicated;
    }''',
        "PM4 packet predicate bit accessor")
    s = replace_once(s,
        '''    VAddr indirect_args_addr{};
    u32 num_counter_pairs{};
    u64 pixel_counter{};''',
        '''    VAddr indirect_args_addr{};
    u32 num_counter_pairs{};
    u64 pixel_counter{}; // unused by real ZPASS when a Vulkan rasterizer is bound
    bool packet_predicated{};
    std::optional<std::pair<u32, u32>> saved_index_base{};''',
        "predicate and index-base lifecycle")
    s = replace_once(s,
        "    void ProcessCommands();",
        "    void RestorePredicatedIndexBase();\n    void ProcessCommands();",
        "restore predicate index base function")
    path.write_text(s)

    path = core / "amdgpu/liverpool.cpp"
    s = path.read_text()
    s = replace_once(s,
        '''Liverpool::Task Liverpool::ProcessGraphics(std::span<const u32> dcb, std::span<const u32> ccb) {''',
        '''void Liverpool::RestorePredicatedIndexBase() {
    if (!saved_index_base)
        return;
    regs.index_base_address.base_addr_lo = saved_index_base->first;
    regs.index_base_address.base_addr_hi = saved_index_base->second;
    MarkRegs(&regs.index_base_address, sizeof(regs.index_base_address));
    saved_index_base.reset();
}

Liverpool::Task Liverpool::ProcessGraphics(std::span<const u32> dcb, std::span<const u32> ccb) {''',
        "revert index base from skipped GPU-predicated draw")
    s = replace_once(s,
        '''    const auto base_addr = reinterpret_cast<uintptr_t>(dcb.data());
    while (!dcb.empty()) {''',
        '''    auto* const predication = rasterizer ? &rasterizer->GetPredication() : nullptr;
    const auto base_addr = reinterpret_cast<uintptr_t>(dcb.data());
    while (!dcb.empty()) {''',
        "bind current graphics queue to actual GPU predication")
    s = replace_once(s,
        '''            const u32 count = header->type3.NumWords();
            const PM4ItOpcode opcode = header->type3.opcode;
            switch (opcode) {''',
        '''            const u32 count = header->type3.NumWords();
            const PM4ItOpcode opcode = header->type3.opcode;
            packet_predicated = header->type3.predicate == PM4Predicate::PredEnable;
            if (packet_predicated && predication && predication->ShouldSkipPredicatedPacket()) {
                // A static, known-false predicate: no PM4 side effects and no draw.
                const size_t skip = count + 1;
                dcb = NextPacket(dcb, skip);
                continue;
            }
            switch (opcode) {''',
        "skip static-false predicated graphics packets")
    s = replace_once(s,
        '''            case PM4ItOpcode::SetPredication: {
                // sotc: once; the game sends it every frame.
                static bool reported = false;
                if (!std::exchange(reported, true)) {
                    LOG_WARNING(Render, "Unimplemented IT_SET_PREDICATION (reported once)");
                }
                break;
            }''',
        '''            case PM4ItOpcode::SetPredication: {
                const auto* set_pred = reinterpret_cast<const PM4CmdSetPredication*>(header);
                RestorePredicatedIndexBase();
                if (!predication)
                    break;
                const auto op = set_pred->pred_op.Value();
                const bool visible = set_pred->draw_visible.Value() != 0;
                const bool combine = set_pred->continue_predication.Value() != 0;
                switch (op) {
                case PredicationOp::Clear:
                    predication->Disable();
                    break;
                case PredicationOp::Zpass:
                    predication->EnableFromZpass(set_pred->Address(), num_counter_pairs,
                                                 visible, combine);
                    break;
                case PredicationOp::Bool32:
                case PredicationOp::Bool64:
                    predication->EnableFromBool(set_pred->Address(),
                                                op == PredicationOp::Bool64, visible, combine);
                    break;
                default:
                    LOG_WARNING(Render, "Unsupported IT_SET_PREDICATION op {} addr={:#x}",
                                u32(op), set_pred->Address());
                    predication->Disable(); // fail open, never hide unknown geometry
                    break;
                }
                static u32 logged{};
                if (logged++ < 8)
                    std::fprintf(stderr,
                        "SotC PM4 predicate op=%u addr=%#llx visible=%d combine=%d gpu=%d\\n",
                        u32(op), static_cast<unsigned long long>(set_pred->Address()),
                        int(visible), int(combine), int(predication->IsGpuPredicationActive()));
                break;
            }''',
        "parse actual PM4 predication op and consume real ZPASS")
    s = replace_once(s,
        '''            case PM4ItOpcode::DrawIndex2: {
                const auto* draw_index = reinterpret_cast<const PM4CmdDrawIndex2*>(header);
                regs.max_index_size''',
        '''            case PM4ItOpcode::DrawIndex2: {
                const auto* draw_index = reinterpret_cast<const PM4CmdDrawIndex2*>(header);
                // The index-base register update of a GPU-predicated draw may not
                // execute; restore it before the next unconditional draw.
                if (packet_predicated && predication && predication->IsGpuPredicationActive()) {
                    if (!saved_index_base) {
                        saved_index_base.emplace(
                            static_cast<u32>(regs.index_base_address.base_addr_lo),
                            static_cast<u32>(regs.index_base_address.base_addr_hi));
                    }
                } else {
                    saved_index_base.reset();
                }
                regs.max_index_size''',
        "predicated draw index-base isolation")
    s = replace_once(s,
        '''                } else if (event->event_index.Value() == EventIndex::ZpassDone) {
                    if (event->event_type.Value() == EventType::PixelPipeStatDump) {''',
        '''                } else if (event->event_type.Value() == EventType::PixelPipeStatReset) {
                    if (predication) predication->ResetZpassCounting();
                } else if (event->event_type.Value() == EventType::PixelPipeStatControl) {
                    if (predication) predication->ControlZpassCounting();
                } else if (event->event_index.Value() == EventIndex::ZpassDone) {
                    if (event->event_type.Value() == EventType::PixelPipeStatDump) {
                        if (predication) {
                            predication->DumpZpassCounters(event->Address<VAddr>(),
                                                          num_counter_pairs);
                            break;
                        }''',
        "pixel-pipe stats become real GPU occlusion query records")
    s = replace_once(s,
        '''            case PM4ItOpcode::CondExec: {
                const auto* cond_exec = reinterpret_cast<const PM4CmdCondExec*>(header);''',
        '''            case PM4ItOpcode::PredExec: {
                const auto* packet = reinterpret_cast<const PM4CmdPredExec*>(header);
                if (predication && predication->ShouldSkipPredicatedPacket()) {
                    dcb = NextPacket(dcb, count + 1 + packet->exec_count.Value());
                    continue;
                }
                // A GPU-side predicate cannot be checked on CPU; safe fail open.
                break;
            }
            case PM4ItOpcode::CondExec: {
                const auto* cond_exec = reinterpret_cast<const PM4CmdCondExec*>(header);''',
        "PM4 pred_exec static predicate")
    path.write_text(s)

    path = vk = core / "renderer_vulkan/vk_rasterizer.h"
    s = path.read_text()
    s = replace_once(s,
        '#include "video_core/renderer_vulkan/vk_rasterizer.h"',
        '#include "video_core/renderer_vulkan/vk_rasterizer.h"',
        "NOOP") if False else s
    # Keep manager AFTER buffer_cache so references in its ctor are valid.
    s = replace_once(s,
        "    VideoCore::BufferCache buffer_cache;\n    VideoCore::TextureCache texture_cache;",
        "    VideoCore::BufferCache buffer_cache;\n"
        "    PredicationManager predication;\n"
        "    VideoCore::TextureCache texture_cache;",
        "Vulkan rasterizer real predication manager lifetime")
    s = replace_once(s,
        "    [[nodiscard]] VideoCore::BufferCache& GetBufferCache() noexcept {",
        '''    PredicationManager& GetPredication() noexcept {
        return predication;
    }

    [[nodiscard]] VideoCore::BufferCache& GetBufferCache() noexcept {''',
        "Vulkan rasterizer predication accessor")
    s = replace_once(s, '#include "video_core/buffer_cache/buffer_cache.h"',
        '#include "video_core/buffer_cache/buffer_cache.h"\n'
        '#include "video_core/renderer_vulkan/vk_predication.h"',
        "predication manager declaration include") if '#include "video_core/buffer_cache/buffer_cache.h"' in s else s
    if '#include "video_core/renderer_vulkan/vk_predication.h"' not in s:
        # A different header arrangement is possible; still insert an exact include.
        s = replace_once(s, "#pragma once",
          '#pragma once\n#include "video_core/renderer_vulkan/vk_predication.h"',
          "predication header inclusion")
    path.write_text(s)

    path = core / "renderer_vulkan/vk_rasterizer.cpp"
    s = path.read_text()
    s = replace_once(s,
        '''      buffer_cache{instance, scheduler, runtime, liverpool_, texture_cache, page_manager},
      texture_cache{instance, scheduler, runtime, liverpool_, buffer_cache, page_manager},''',
        '''      buffer_cache{instance, scheduler, runtime, liverpool_, texture_cache, page_manager},
      predication{instance_, scheduler_, buffer_cache},
      texture_cache{instance, scheduler, runtime, liverpool_, buffer_cache, page_manager},''',
        "predication initialization after buffer cache")
    # Query reset needs to happen outside dynamic rendering; the queries must be
    # begun and ended strictly around the PRIMARY draw, not the HUD composite replay.
    s = replace_once(s,
        '''    if (!fast_bind_hit) {
        pipeline->BindResources(set_writes, push_data);
    }
    UpdateDynamicState(pipeline, is_indexed);
    scheduler.BeginRendering(state);

    const auto& vs_info''',
        '''    if (!fast_bind_hit) {
        pipeline->BindResources(set_writes, push_data);
    }
    const auto zpass_query = predication.PrepareDrawQuery();
    UpdateDynamicState(pipeline, is_indexed);
    scheduler.BeginRendering(state);

    const auto& vs_info''',
        "prepare occlusion query before graphics primary draw")
    s = replace_once(s,
        '''    cmdbuf.bindPipeline(vk::PipelineBindPoint::eGraphics, pipeline->Handle());

    if (is_indexed) {
        cmdbuf.drawIndexed(regs.num_indices''',
        '''    cmdbuf.bindPipeline(vk::PipelineBindPoint::eGraphics, pipeline->Handle());
    predication.BeginDraw(cmdbuf, zpass_query, liverpool->IsPacketPredicated());
    if (is_indexed) {
        cmdbuf.drawIndexed(regs.num_indices''',
        "begin conditional rendering on primary direct draw")
    s = replace_once(s,
        '''        cmdbuf.draw(regs.num_indices, regs.num_instances.NumInstances(), vertex_offset,
                    instance_offset);
    }
    // sotc: the final composite again''',
        '''        cmdbuf.draw(regs.num_indices, regs.num_instances.NumInstances(), vertex_offset,
                    instance_offset);
    }
    predication.EndDraw(cmdbuf, zpass_query, liverpool->IsPacketPredicated());
    // sotc: the final composite again''',
        "end conditional rendering around direct draw")
    s = replace_once(s,
        '''    const auto state = BeginRendering(pipeline);
    ui_shadow_broken |= ui_shadow_hit;''',
        '''    const auto zpass_query = predication.PrepareDrawQuery();
    const auto state = BeginRendering(pipeline);
    ui_shadow_broken |= ui_shadow_hit;''',
        "prepare query for indirect draw")
    s = replace_once(s,
        '''        cmdbuf.bindPipeline(vk::PipelineBindPoint::eGraphics, pipeline->Handle());
        if (is_indexed) {
            const auto& a = args.indexed;''',
        '''        cmdbuf.bindPipeline(vk::PipelineBindPoint::eGraphics, pipeline->Handle());
        predication.BeginDraw(cmdbuf, zpass_query, liverpool->IsPacketPredicated());
        if (is_indexed) {
            const auto& a = args.indexed;''',
        "direct-args fast path predicate begin")
    s = replace_once(s,
        '''            cmdbuf.draw(a.vertexCount, a.instanceCount, a.firstVertex, a.firstInstance);
        }
        DebugState.IncDrawCall();''',
        '''            cmdbuf.draw(a.vertexCount, a.instanceCount, a.firstVertex, a.firstInstance);
        }
        predication.EndDraw(cmdbuf, zpass_query, liverpool->IsPacketPredicated());
        DebugState.IncDrawCall();''',
        "direct-args predicate end")
    s = replace_once(s,
        '''    const auto cmdbuf = scheduler.CommandBuffer();
    cmdbuf.bindPipeline(vk::PipelineBindPoint::eGraphics, pipeline->Handle());

    if (is_indexed) {
        ASSERT(sizeof(VkDrawIndexedIndirectCommand) == stride);''',
        '''    const auto cmdbuf = scheduler.CommandBuffer();
    cmdbuf.bindPipeline(vk::PipelineBindPoint::eGraphics, pipeline->Handle());
    predication.BeginDraw(cmdbuf, zpass_query, liverpool->IsPacketPredicated());
    if (is_indexed) {
        ASSERT(sizeof(VkDrawIndexedIndirectCommand) == stride);''',
        "GPU-native indirect draw predicate begin")
    s = replace_once(s,
        '''        DebugState.IncDrawCall();
    }

    // Record the indirect argument reads''',
        '''        DebugState.IncDrawCall();
    }
    predication.EndDraw(cmdbuf, zpass_query, liverpool->IsPacketPredicated());

    // Record the indirect argument reads''',
        "GPU-native indirect draw predicate end")
    path.write_text(s)
    print("SotC predication: real SetPredication/PixelPipeStatDump and Vulkan draw queries integrated")

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--gpu", type=Path, required=True)
    patch(p.parse_args().gpu)
