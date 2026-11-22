#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""SotC ARM64 native renderer: reversible *benchmark* of sun shadow cascade work.

SOTC_SUN_CASCADES=5 (default original), 3, 2, 1, 0 (all sun cascades disabled).
The target is detected from the previous frame's highest draw-count square depth
map with >=500 draws, exactly as in upstream SkipStaggeredShadow. Other shadow
maps, depth passes, color passes and every guest PM4 command are preserved.

Draws into excluded cascades are not prepared/bound/submitted; each excluded
depth slice is cleared ONCE per frame to the exact guest depth-clear value to
avoid sampling stale sun shadows. No other shadows or shader outputs modified.
The first frame is always unmodified, while the sun map classifier warms up.

IMPORTANT: this is a controlled CPU/GPU attribution experiment, not a visual
quality-preserving game optimization. Reducing cascades removes real shadows.
"""
from pathlib import Path

CPP = r"""
// Experimental SotC performance control; never run unless explicitly selected
// through the launcher. A zero setting means the *detected sun* cascades are
// depth-cleared, not left with shadows from an old frame. Other depth targets
// and every incoming PM4 packet retain their original behavior.
bool Rasterizer::SkipSunShadowBenchmark() {
#if !defined(__aarch64__)
    return false;
#else
    static const u32 keep = [] {
        const char* value = std::getenv("SOTC_SUN_CASCADES");
        if (!value || !*value) return 5u;
        if (std::strcmp(value, "0") == 0) return 0u;
        if (std::strcmp(value, "1") == 0) return 1u;
        if (std::strcmp(value, "2") == 0) return 2u;
        if (std::strcmp(value, "3") == 0) return 3u;
        return 5u;
    }();
    if (keep >= 5) return false;

    const auto& regs = liverpool->DrawRegs();
    const u64 frame = SotcStats::flip_count.load(std::memory_order_relaxed);
    static u64 frame_seen = ~u64{0};
    static u64 sun_map = 0;
    static std::unordered_map<u64, u32> candidates;
    static std::array<u64, 8> cleared_frame{};
    static std::array<u64, 8> cleared_uid{};
    static u64 skipped = 0, clears = 0, refused = 0;
    if (frame != frame_seen) {
        // The selector uses the PREVIOUS frame's draw counts; those are
        // incremented even when their operations were intentionally skipped.
        u64 winner = 0;
        u32 most = 0;
        for (const auto& [addr, count] : candidates) {
            if (count > most) {
                most = count;
                winner = addr;
            }
        }
        const u64 next = most >= 500 ? winner : 0;
        if (next != sun_map) {
            cleared_frame.fill(~u64{0});
            cleared_uid.fill(0);
        }
        sun_map = next;
        candidates.clear();
        if (frame_seen != ~u64{0} && frame % 300 == 0) {
            std::fprintf(stderr,
                "SOTC SUN CASCADES: keep=%u sun_map=%#llx skipped=%llu cleared=%llu fallback=%llu\n",
                keep, static_cast<unsigned long long>(sun_map),
                static_cast<unsigned long long>(skipped),
                static_cast<unsigned long long>(clears),
                static_cast<unsigned long long>(refused));
            skipped = clears = refused = 0;
        }
        frame_seen = frame;
    }
    if (!regs.depth_buffer.DepthValid() ||
        regs.color_control.mode != AmdGpu::ColorControl::OperationMode::Normal ||
        regs.depth_buffer.Pitch() != regs.depth_buffer.Height() ||
        regs.depth_buffer.Pitch() < 512) {
        return false;
    }
    const u64 addr = regs.depth_buffer.DepthWriteAddress();
    if (!addr) return false;
    ++candidates[addr];
    const u32 first = regs.depth_view.slice_start;
    const u32 last = regs.depth_view.slice_max;
    if (addr != sun_map || first < keep || first >= 8 || first != last) return false;

    // Clear one excluded layer per frame. Without the clear, later lighting
    // reads the last frame's sun-shadow map and falsely shows stale shadows.
    // The depth clear value is taken from the game's own depth state, not
    // guessed as 0 or 1 (SotC may use reverse-Z).
    const auto guard = texture_cache.BatchLock();
    const auto htile = regs.depth_htile_data_base.GetAddress();
    VideoCore::TextureCache::ImageDesc desc(regs.depth_buffer, regs.depth_view,
                                            regs.depth_control, htile,
                                            liverpool->DrawDbExtent());
    const auto image_id = texture_cache.FindImage(desc);
    texture_cache.FindRenderTarget(image_id, desc);
    auto& image = texture_cache.GetImage(image_id);
    if (!image.info.props.is_depth || !image.backing ||
        !(image.aspect_mask & vk::ImageAspectFlagBits::eDepth) ||
        desc.view_info.range.extent.layers != 1 ||
        desc.view_info.range.base.layer != first) {
        ++refused;
        return false; // never skip unless the no-shadow depth clear is possible
    }

    if (cleared_frame[first] != frame || cleared_uid[first] != image.image_uid) {
        scheduler.EndRendering();
        const auto& range = desc.view_info.range;
        const bool barrier = runtime.Transit(
            &image, vk::ImageLayout::eTransferDstOptimal,
            vk::PipelineStageFlagBits2::eClear,
            vk::AccessFlagBits2::eTransferWrite, range);
        if (barrier) runtime.FlushBarriers();
        const vk::ImageSubresourceRange vk_range{
            .aspectMask = vk::ImageAspectFlagBits::eDepth,
            .baseMipLevel = range.base.level,
            .levelCount = range.extent.levels,
            .baseArrayLayer = range.base.layer,
            .layerCount = range.extent.layers,
        };
        scheduler.CommandBuffer().clearDepthStencilImage(
            image.GetImage(), vk::ImageLayout::eTransferDstOptimal,
            vk::ClearDepthStencilValue{regs.depth_clear, 0}, vk_range);
        VideoCore::MarkGpuModified(image);
        image.flags &= ~VideoCore::ImageFlagBits::Dirty;
        cleared_frame[first] = frame;
        cleared_uid[first] = image.image_uid;
        ++clears;
    }
    ++skipped;
    return true;
#endif
}

"""

def patch(gpu: Path) -> None:
    renderer = gpu / "shadps4/video_core/renderer_vulkan"
    source = renderer / "vk_rasterizer.cpp"
    text = source.read_text()
    marker = "// sotc: TakeHudless (vk_rasterizer.h)."
    if text.count(marker) != 1:
        raise ValueError("Sun cascade patch: expected single renderer insertion point")
    if text.count("    if (SkipStaggeredShadow(liverpool->DrawRegs()) || ReuseShadowCascade()) {") != 2:
        raise ValueError("Sun cascade patch: expected direct and indirect draw path")
    if "SOTC SUN CASCADES:" in text:
        raise ValueError("Sun cascade patch: already applied")
    for needed in (
        "texture_cache.FindImage(desc)",
        "texture_cache.FindRenderTarget(image_id, desc)",
        "VideoCore::MarkGpuModified",
        "SotcStats::flip_count.load",
        "regs.depth_clear",
    ):
        if needed not in text:
            raise ValueError("Sun cascade patch: upstream invariant missing " + needed)
    text = text.replace(marker, CPP + marker)
    text = text.replace(
        "    if (SkipStaggeredShadow(liverpool->DrawRegs()) || ReuseShadowCascade()) {",
        "    if (SkipSunShadowBenchmark() ||\n"
        "        SkipStaggeredShadow(liverpool->DrawRegs()) || ReuseShadowCascade()) {")
    source.write_text(text)

    hpath = renderer / "vk_rasterizer.h"
    header = hpath.read_text()
    signature = "    bool ReuseShadowCascade();"
    if header.count(signature) != 1:
        raise ValueError("Sun cascade patch: rasterizer header signature changed")
    header = header.replace(signature,
        "    // Benchmark: safely clear excluded sun shadow layers before skipping draw calls.\n"
        "    bool SkipSunShadowBenchmark();\n" + signature)
    hpath.write_text(header)
    print("SotC sun cascade benchmark: 5,3,2,1,0; excluded layers clear to guest depth; no other passes skipped")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gpu", required=True, type=Path)
    patch(parser.parse_args().gpu)
