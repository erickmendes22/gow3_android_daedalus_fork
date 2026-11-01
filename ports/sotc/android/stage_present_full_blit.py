#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Remove redundant SotC AHB transfer clear only for a full-screen blit.

The original vk_presenter.cpp clears the whole destination, inserts a
transfer-write barrier, then unconditionally overwrites that image by blit.
The black-border clear AND its barrier must remain when FitImage does not cover
the entire surface. This is a GPU bandwidth/barrier fastpath only, not a skip
of real game render work, and can be disabled with SOTC_PRESENT_FULL_BLIT=0.
"""
from pathlib import Path


def patch_present_full_blit(gpu: Path) -> None:
    path = gpu / "shadps4/video_core/renderer_vulkan/vk_presenter.cpp"
    s = path.read_text()
    old_rect = "            const auto rect = FitImage(frame->width, frame->height, extent.width, extent.height);"
    clear = ("            cmdbuf.clearColorImage(swapchain_image, vk::ImageLayout::eTransferDstOptimal,\n"
             "                                   vk::ClearColorValue{std::array<float, 4>{0.f, 0.f, 0.f, 1.f}},\n"
             "                                   color_range);")
    barrier = ("            cmdbuf.pipelineBarrier(vk::PipelineStageFlagBits::eTransfer,\n"
               "                                   vk::PipelineStageFlagBits::eTransfer, {}, {}, {},\n"
               "                                   clear_to_blit);\n"
               "            const auto rect = FitImage(frame->width, frame->height, extent.width, extent.height);")
    if s.count(old_rect) != 1 or s.count(clear) != 1 or s.count(barrier) != 1:
        raise ValueError("SotC presenter changed; refusing ambiguous clear/barrier patch")

    prefix = """            // Safe only when every destination pixel is overwritten by the blit.
            // AHB letterbox bars, cropped surfaces or partial blits still get the
            // original black clear AND its transfer-write -> write barrier.
            const auto rect = FitImage(frame->width, frame->height, extent.width, extent.height);
            static const bool skip_full_blit_clear = [] {
                const char* value = std::getenv("SOTC_PRESENT_FULL_BLIT");
                return !value || value[0] != '0';
            }();
            const bool needs_black_clear = !skip_full_blit_clear ||
                rect.offset.x != 0 || rect.offset.y != 0 ||
                rect.extent.width != extent.width || rect.extent.height != extent.height;
            if (needs_black_clear) {
"""
    # Remove the old rect declaration only at the barrier end first.
    s = s.replace(barrier, barrier.replace(old_rect, "            } // Clear and barrier required only for partial destination blits."), 1)
    s = s.replace(clear, prefix + clear, 1)
    if s.count("const auto rect = FitImage(frame->width, frame->height, extent.width, extent.height);") != 1:
        raise AssertionError("SotC fullscreen blit now has multiple/missing rects")
    if s.index("if (needs_black_clear)") >= s.index(clear):
        raise AssertionError("Clear was not guarded before the memory writes")
    path.write_text(s)
    print("SotC presenter full-coverage blit fastpath: skip redundant clear+barrier; keep both for letterbox")


if __name__ == "__main__":
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("--gpu", type=Path, required=True)
    patch_present_full_blit(ap.parse_args().gpu)
