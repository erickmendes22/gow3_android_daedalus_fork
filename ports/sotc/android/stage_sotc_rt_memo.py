#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Source-only opt-in render-state memo. No APR/APK or behavior changes by default.
Never bypass SotC CMASK, HTILE, HUD side effects, data uploads, or barriers.
"""
from pathlib import Path

HEADER_REPLACEMENT = "    RenderState BeginRendering(const GraphicsPipeline* pipeline);\n    RenderState BeginRenderingFull(const GraphicsPipeline* pipeline);\n    // Cached only while the same Vulkan rendering scope is still active.\n    struct RtMemoSignature {\n        std::array<VideoCore::ImageId, AmdGpu::NUM_COLOR_BUFFERS + 1> ids{};\n        std::array<VideoCore::ImageViewInfo, AmdGpu::NUM_COLOR_BUFFERS + 1> views{};\n        std::array<VAddr, AmdGpu::NUM_COLOR_BUFFERS> cmask{};\n        VAddr htile{};\n        u32 mrt_mask{}, depth_control{}, depth_render_control{}, color_mode{};\n        u64 registry_generation{};\n        u8 num_samples{}, depth_samples{};\n        std::array<u8, AmdGpu::NUM_COLOR_BUFFERS> color_samples{};\n        bool depth_valid{}, stencil_valid{};\n        bool operator==(const RtMemoSignature&) const = default;\n    };\n    RtMemoSignature MakeRtMemoSignature(const GraphicsPipeline* pipeline) const;\n    struct RtMemo {\n        bool valid{};\n        RtMemoSignature sig{};\n        RenderState state{};\n    } rt_memo{};\n    bool RtMemoAttachmentsSafe(const RtMemoSignature& sig);\n    void RefreshImageLayouts();"
CPP_REPLACEMENT = "Rasterizer::RtMemoSignature\nRasterizer::MakeRtMemoSignature(const GraphicsPipeline* pipeline) const {\n    RtMemoSignature s{};\n    const auto& key = pipeline->GetGraphicsKey();\n    const auto& regs = liverpool->DrawRegs();\n    s.mrt_mask = key.mrt_mask;\n    s.num_samples = key.num_samples;\n    s.depth_samples = key.depth_samples;\n    s.color_samples = key.color_samples;\n    s.color_mode = static_cast<u32>(regs.color_control.mode);\n    s.registry_generation = texture_cache.BindGeneration();\n    static_assert(sizeof(regs.depth_control) == sizeof(u32));\n    static_assert(sizeof(regs.depth_render_control) == sizeof(u32));\n    std::memcpy(&s.depth_control, &regs.depth_control, sizeof(u32));\n    std::memcpy(&s.depth_render_control, &regs.depth_render_control, sizeof(u32));\n    s.depth_valid = regs.depth_buffer.DepthValid();\n    s.stencil_valid = regs.depth_buffer.StencilValid();\n    for (u32 i = 0; i < std::bit_width(key.mrt_mask); ++i) {\n        s.ids[i] = cb_descs[i].first;\n        if (s.ids[i]) {\n            s.views[i] = cb_descs[i].second.view_info;\n            s.cmask[i] = regs.color_buffers[i].CmaskAddress();\n        }\n    }\n    s.ids[AmdGpu::NUM_COLOR_BUFFERS] = db_desc.first;\n    if (db_desc.first) {\n        s.views[AmdGpu::NUM_COLOR_BUFFERS] = db_desc.second.view_info;\n        s.htile = regs.depth_htile_data_base.GetAddress();\n    }\n    return s;\n}\n\nbool Rasterizer::RtMemoAttachmentsSafe(const RtMemoSignature& sig) {\n    const auto& regs = liverpool->DrawRegs();\n    if (regs.depth_render_control.depth_clear_enable ||\n        regs.depth_render_control.stencil_clear_enable) {\n        return false;\n    }\n    for (u32 i = 0; i < std::bit_width(sig.mrt_mask); ++i) {\n        const auto id = sig.ids[i];\n        if (!id) continue;\n        const auto& image = texture_cache.GetImage(id);\n        if (!image.backing || image.binding.is_bound || image.binding.needs_rebind ||\n            static_cast<u32>(image.flags & VideoCore::ImageFlagBits::Dirty) ||\n            image.backing->state.layout != rt_memo.state.color_attachments[i].image_layout) {\n            return false;\n        }\n        if (texture_cache.IsMetaCleared(sig.cmask[i], sig.views[i].range.base.layer))\n            return false;\n        // HUD-less and UI-shadow re-rendering are SotC draw side effects.\n        if (i == 0 && (image.usage.vo_surface ||\n                       Dlssg::UiTarget(image.info.guest_address,\n                                       image.info.size.width, image.info.size.height,\n                                       ui_shadow_width, ui_shadow_height)))\n            return false;\n    }\n    const auto depth_id = sig.ids[AmdGpu::NUM_COLOR_BUFFERS];\n    if (depth_id) {\n        const auto& image = texture_cache.GetImage(depth_id);\n        if (!image.backing || image.binding.is_bound || image.binding.needs_rebind ||\n            static_cast<u32>(image.flags & VideoCore::ImageFlagBits::Dirty) ||\n            image.backing->state.layout != rt_memo.state.depth_stencil_attachment.image_layout ||\n            texture_cache.IsMetaCleared(sig.htile,\n                sig.views[AmdGpu::NUM_COLOR_BUFFERS].range.base.layer))\n            return false;\n    }\n    return true;\n}\n\nRenderState Rasterizer::BeginRendering(const GraphicsPipeline* pipeline) {\n#if defined(__aarch64__)\n    // Disabled until tested on the device. No draw/bind/readback path skipped.\n    static const bool enabled = [] {\n        const char* v = std::getenv(\"SOTC_RT_MEMO\");\n        return v && v[0] == '1';\n    }();\n    if (enabled) {\n        // Lock covers metadata and the dirty/target checks. Original function\n        // takes the same reentrant lock again only on a cache miss.\n        const auto lock = texture_cache.BatchLock();\n        const RtMemoSignature sig = MakeRtMemoSignature(pipeline);\n        if (rt_memo.valid && sig == rt_memo.sig && !needs_barrier &&\n            !attachment_feedback_loop && scheduler.IsRendering() &&\n            scheduler.GetRenderState() == rt_memo.state && RtMemoAttachmentsSafe(sig)) {\n            ui_shadow_hit = false;\n            return rt_memo.state;\n        }\n        rt_memo.valid = false;\n        RenderState state = BeginRenderingFull(pipeline);\n        bool clears = state.depth_stencil_attachment.depth_clear ||\n                      state.depth_stencil_attachment.stencil_clear;\n        for (u32 i = 0; i < state.num_color_attachments; ++i)\n            clears |= state.color_attachments[i].is_clear != 0;\n        if (!clears && !needs_barrier && !attachment_feedback_loop)\n            rt_memo = {true, MakeRtMemoSignature(pipeline), state};\n        return state;\n    }\n#endif\n    return BeginRenderingFull(pipeline);\n}\n\nRenderState Rasterizer::BeginRenderingFull(const GraphicsPipeline* pipeline) {"

def once(s, old, new, what):
    n=s.count(old)
    if n != 1:
        raise ValueError(f"SotC RT memo source drift: {what} ({n})")
    return s.replace(old,new)

def patch_sotc_rt_memo(gpu: Path) -> None:
    renderer=Path(gpu)/"shadps4/video_core/renderer_vulkan"
    hpath=renderer/"vk_rasterizer.h"
    cpath=renderer/"vk_rasterizer.cpp"
    h=once(hpath.read_text(),
           "    RenderState BeginRendering(const GraphicsPipeline* pipeline);\n    void RefreshImageLayouts();",
           HEADER_REPLACEMENT,"header")
    c=once(cpath.read_text(),
           "RenderState Rasterizer::BeginRendering(const GraphicsPipeline* pipeline) {",
           CPP_REPLACEMENT,"renderer")
    for marker in ("texture_cache.TestAndTouchMeta(col_buf.CmaskAddress(), slice)",
                   "texture_cache.TestAndTouchMeta(htile_address, slice)",
                   "RefreshImageLayouts();","scheduler.BeginRendering(state);",
                   "bool Rasterizer::BindResources"):
        if marker not in c:
            raise ValueError(f"SotC RT memo invariant absent: {marker}")
    hpath.write_text(h)
    cpath.write_text(c)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--gpu",type=Path,required=True)
    patch_sotc_rt_memo(p.parse_args().gpu)
