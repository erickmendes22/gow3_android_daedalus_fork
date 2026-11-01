#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Android-only, exact-state CPU/Vulkan fast paths for pinned SotC renderer.

Separate from SOTC_FAST_BIND (unsafe when guest memory changes at same address):
- VkCmdBindPipeline memo skips only an unchanged host Vulkan pipeline command.
- VkCmdSetVertexInputEXT memo caches complete explicit Vk state, NOT guest buffers.
- Descriptor write slots persist but are fully zero-reset before every draw and
  every resource lookup/barrier/push-constant operation still takes place.

The real graphics and readback paths are never skipped. Source-anchored edits
fail closed if the upstream renderer changes.
"""
from pathlib import Path
import shutil


def swap(text: str, old: str, new: str, label: str, count: int = 1) -> str:
    actual = text.count(old)
    if actual != count:
        raise ValueError(f"SotC fastpaths source drift: {label}: expected {count}, got {actual}")
    return text.replace(old, new)


def patch_fastpaths(root: Path, gpu: Path) -> None:
    renderer = gpu / "shadps4/video_core/renderer_vulkan"
    header = root / "ports/sotc/android/vk_sotc_fastpaths.h"
    if not header.is_file():
        raise ValueError("SotC exact-state fastpath header is missing")
    shutil.copy2(header, renderer / "vk_sotc_fastpaths.h")

    scheduler_header = renderer / "vk_scheduler.h"
    h = scheduler_header.read_text()
    h = swap(h, "    bool is_rendering = false;",
             "    bool is_rendering = false;\n"
             "    // Updated when another render scope changes Vulkan graphics state.\n"
             "    u64 sotc_fastpath_epoch{};",
             "scheduler invalidate-on-pass epoch")
    h = swap(h, "    /// Returns the current command buffer tick.",
             "    // Host Vulkan-state memos never cross a rendering-scope boundary.\n"
             "    [[nodiscard]] u64 SotcFastpathEpoch() const noexcept {\n"
             "        return sotc_fastpath_epoch;\n"
             "    }\n\n"
             "    /// Returns the current command buffer tick.",
             "scheduler graphics binding-state epoch accessor")
    scheduler_header.write_text(h)

    scheduler_source = renderer / "vk_scheduler.cpp"
    s = scheduler_source.read_text()
    s = swap(s, "    is_rendering = false;\n    CommandBuffer().endRendering();",
             "    is_rendering = false;\n"
             "    ++sotc_fastpath_epoch; // any subsequent draw must rebind host state\n"
             "    CommandBuffer().endRendering();",
             "scheduler render-scope invalidation")
    scheduler_source.write_text(s)

    rasterizer = renderer / "vk_rasterizer.cpp"
    r = rasterizer.read_text()
    r = swap(r, '#include "video_core/renderer_vulkan/vk_rasterizer.h"',
             '#include "video_core/renderer_vulkan/vk_rasterizer.h"\n'
             '#include "video_core/renderer_vulkan/vk_sotc_fastpaths.h"',
             "rasterizer exact-state helpers")
    helpers = r'''
// Host Vulkan recording-state only. Guest memory and resource validation remain
// in the original Draw/DrawIndirect/BindResources paths on EVERY draw.
namespace SotcPerf {
static bool PipelineMemoEnabled() {
    static const bool enabled = [] {
        const char* value = std::getenv("SOTC_PIPELINE_BIND_MEMO");
        return !value || value[0] != '0';
    }();
    return enabled;
}
static bool VertexMemoEnabled() {
    static const bool enabled = [] {
        const char* value = std::getenv("SOTC_VERTEX_INPUT_MEMO");
        return !value || value[0] != '0';
    }();
    return enabled;
}
static bool DescriptorSlotsEnabled() {
    static const bool enabled = [] {
        const char* value = std::getenv("SOTC_DESCRIPTOR_SLOT_REUSE");
        return !value || value[0] != '0';
    }();
    return enabled;
}
static void BindGraphicsPipeline(vk::CommandBuffer cmdbuf, vk::Pipeline handle,
                                 u64 tick, u64 render_epoch) {
    if (PipelineMemoEnabled()) {
        static thread_local SotcFastPath::GraphicsPipelineMemo<vk::CommandBuffer, vk::Pipeline>
            memo;
        if (!memo.NeedsBind(cmdbuf, handle, tick, render_epoch)) {
            return;
        }
    }
    cmdbuf.bindPipeline(vk::PipelineBindPoint::eGraphics, handle);
}
template<class Bindings, class Attributes>
static void SetVertexInput(vk::CommandBuffer cmdbuf, u64 tick, u64 render_epoch,
                           const Bindings& bindings, const Attributes& attributes) {
    if (VertexMemoEnabled()) {
        static thread_local SotcFastPath::VertexInputMemo<
            vk::CommandBuffer, vk::VertexInputBindingDescription2EXT,
            vk::VertexInputAttributeDescription2EXT> memo;
        using B = vk::VertexInputBindingDescription2EXT;
        using A = vk::VertexInputAttributeDescription2EXT;
        if (!memo.NeedsSet(cmdbuf, tick, render_epoch,
                           std::span<const B>{bindings.data(), bindings.size()},
                           std::span<const A>{attributes.data(), attributes.size()})) {
            return;
        }
    }
    cmdbuf.setVertexInputEXT(bindings, attributes);
}
} // namespace SotcPerf

'''
    r = swap(r, "namespace Vulkan {\n\nstatic Shader::PushData",
             "namespace Vulkan {\n\n" + helpers + "static Shader::PushData",
             "rasterizer host Vulkan memo functions")
    r = swap(r, "    cmdbuf.bindPipeline(vk::PipelineBindPoint::eGraphics, pipeline->Handle());",
             "    SotcPerf::BindGraphicsPipeline(cmdbuf, pipeline->Handle(),\n"
             "                                   scheduler.CurrentTick(), scheduler.SotcFastpathEpoch());",
             "all three direct and indirect host graphics pipeline binds", count=3)
    r = swap(r, "        cmdbuf.setVertexInputEXT(bindings, attributes);",
             "        SotcPerf::SetVertexInput(cmdbuf, scheduler.CurrentTick(),\n"
             "                                 scheduler.SotcFastpathEpoch(), bindings, attributes);",
             "set complete Vulkan dynamic vertex input", count=1)

    # Retain the allocation and descriptor objects across calls, while resetting
    # every slot to an empty VkWriteDescriptorSet before any pointer is assigned.
    # Conservative opt-out runs the original clear/per-stage resize byte-for-byte.
    r = swap(r, "    set_write_index = 0;\n    set_writes.clear();",
             "    set_write_index = 0;\n"
             "    const bool reuse_descriptor_slots = SotcPerf::DescriptorSlotsEnabled();\n"
             "    if (!reuse_descriptor_slots) set_writes.clear();",
             "descriptor slots opt-out baseline")
    r = swap(r,
             "    // Bind resource buffers and textures.\n"
             "    Shader::Backend::Bindings binding{};\n"
             "    for (const auto* stage : pipeline->GetStages()) {",
             "    // Recycle, but fully reinitialize each VkWriteDescriptorSet. In particular\n"
             "    // pImageInfo and pBufferInfo may point into arrays rebuilt this draw.\n"
             "    // Never reuse previous guest descriptors, handle generations, or barriers.\n"
             "    if (reuse_descriptor_slots) {\n"
             "        size_t count = 0;\n"
             "        for (const auto* stage : pipeline->GetStages()) {\n"
             "            if (stage) count += stage->buffers.size() + stage->images.size() +\n"
             "                                stage->samplers.size();\n"
             "        }\n"
             "        set_writes.resize(count);\n"
             "        std::fill(set_writes.begin(), set_writes.end(), vk::WriteDescriptorSet{});\n"
             "    }\n"
             "    // Bind resource buffers and textures.\n"
             "    Shader::Backend::Bindings binding{};\n"
             "    for (const auto* stage : pipeline->GetStages()) {",
             "single pass for native descriptor write slot sizing")
    r = swap(r,
             "        set_writes.resize(set_writes.size() + stage->buffers.size() + stage->images.size() +\n"
             "                          stage->samplers.size());",
             "        if (!reuse_descriptor_slots) {\n"
             "            set_writes.resize(set_writes.size() + stage->buffers.size() +\n"
             "                              stage->images.size() + stage->samplers.size());\n"
             "        }",
             "per-stage descriptor writes fallback")
    rasterizer.write_text(r)

    # The blit helper may bind a different graphics pipeline in the same
    # command buffer; it ends the rendering scope, which bumps this epoch.
    blit = gpu / "shadps4/video_core/texture_cache/blit_helper.cpp"
    bt = blit.read_text()
    if bt.count("scheduler.EndRendering();") < 2 or bt.count(
            "cmdbuf.bindPipeline(vk::PipelineBindPoint::eGraphics, *it->second);") != 2:
        raise ValueError("SotC fastpaths: independent blit pipeline invalidation changed upstream")
    blit.write_text(bt)

    print("SotC Android Vulkan fastpaths: exact pipeline memo, full vertex-input memo, "
          "fully reset reusable descriptor slots; 0 opt-outs; rendering scope invalidation")
