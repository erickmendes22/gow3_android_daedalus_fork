#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright 2026
# SPDX-License-Identifier: GPL-2.0-or-later
"""Safe, switchable empty indirect draw fastpath on SotC ARM64.

The last user logs show 4245 scene draws in a single sampled frame.
Only single CPU-backed VkDraw(Indexed)Indirect commands with a provably
zero vertex/index or instance count can skip shader bindings. We still
begin the guest's renderpass to perform every guest depth/color clear.

GPU-written arguments and indirect-count/multi-draw calls are untouched.
The original pipeline lookup, guest PM4 consumption, resource ordering,
and all nonempty draws remain unchanged.
"""
from pathlib import Path

INSERT = r"""
    // Android SotC 0.1.63: a zero-count indirect draw has no shader or vertex
    // invocations, but may still be the FIRST draw of a render pass that clears
    // a color/depth attachment. BeginRendering is essential; dropping the draw
    // before the pass is NOT equivalent (old shadow experiment showed this).
    static const bool empty_bind_fast = [] {
        const char* value = std::getenv("SOTC_INDIRECT_EMPTY_BIND");
        return value && value[0] == '1';
    }();
    if (empty_bind_fast) {
        static u64 seen_frame = ~u64{0};
        static u64 candidate = 0, zero = 0, gpu_arg = 0, unhandled = 0;
        const u64 frame = SotcStats::flip_count.load(std::memory_order_relaxed);
        if (frame != seen_frame) {
            if (seen_frame != ~u64{0} && frame % 300 == 0) {
                std::fprintf(stderr,
                    "SOTC INDIRECT EMPTY BIND: candidates=%llu zero_skips=%llu gpu_args=%llu "
                    "multi_or_count=%llu (last 300 flips, guest clears preserved)\n",
                    static_cast<unsigned long long>(candidate),
                    static_cast<unsigned long long>(zero),
                    static_cast<unsigned long long>(gpu_arg),
                    static_cast<unsigned long long>(unhandled));
                candidate = zero = gpu_arg = unhandled = 0;
            }
            seen_frame = frame;
        }
        const u64 args_addr = arg_address + offset;
        const bool single = count_address == 0 && max_count == 1 &&
            stride == (is_indexed ? sizeof(VkDrawIndexedIndirectCommand)
                                 : sizeof(VkDrawIndirectCommand)) &&
            args_addr >= arg_address;
        if (!single || Dlssg::CapturingInputs()) {
            ++unhandled;
        } else if (buffer_cache.IsRegionGpuModified(args_addr, stride)) {
            // GPU-written arguments must remain on the original Vulkan path.
            ++gpu_arg;
        } else {
            u32 counts[2] = {1, 1};
            if (memory->TryReadBacking(args_addr, counts, sizeof(counts))) {
                ++candidate;
                if (counts[0] == 0 || counts[1] == 0) {
                    // Renderer resources are already prefetched. Vulkan clears
                    // and barriers still execute exactly as a zero-primitive
                    // normal draw would; no sampled images or storage buffers
                    // are needed for zero shader invocations.
                    const auto state = BeginRendering(pipeline);
                    ui_shadow_broken |= ui_shadow_hit;
                    RefreshImageLayouts();
                    if (needs_barrier) runtime.FlushBarriers();
                    scheduler.BeginRendering(state);
                    ResetBindings(false);
                    FlushPeriodic();
                    ++zero;
                    return;
                }
            }
        }
    }
"""

def patch(gpu: Path) -> None:
    source = gpu / "shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp"
    txt = source.read_text()
    header = "void Rasterizer::DrawIndirect(bool is_indexed, VAddr arg_address"
    tail = "// sotc: the two grass compute shaders"
    if txt.count(header) != 1 or txt.count(tail) != 1:
        raise RuntimeError("SotC indirect-zero: upstream draw boundaries drifted")
    a = txt.index(header)
    b = txt.index(tail, a)
    section = txt[a:b]
    target = "    PrepareRenderState(pipeline);\n"
    if section.count(target) != 1:
        raise RuntimeError("SotC indirect-zero: renderer prepare anchor drifted")
    if "SOTC INDIRECT EMPTY BIND:" in txt:
        raise RuntimeError("SotC indirect-zero already applied")
    requirements = (
        "    if (!BindResources(pipeline)) {",
        "    const auto state = BeginRendering(pipeline);",
        "    RefreshImageLayouts();",
        "    ResetBindings(false);",
        "    FlushPeriodic();",
        "    scheduler.BeginRendering(state);",
        "    if (direct_args && count_address == 0 && max_count == 1 &&",
        "buffer_cache.IsRegionGpuModified(arg_address + offset, stride)",
    )
    for invariant in requirements:
        if invariant not in section:
            raise RuntimeError("SotC indirect-zero: upstream invariant changed: " + invariant)
    section = section.replace(target, target + INSERT, 1)
    source.write_text(txt[:a] + section + txt[b:])
    print("SotC indirect empty bind fastpath patched, 0-count guarded, clears retained")

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--gpu", type=Path, required=True)
    patch(p.parse_args().gpu)
