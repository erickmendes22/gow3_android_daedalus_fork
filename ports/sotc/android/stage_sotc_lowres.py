#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Repair the pinned SotC render-size helper for 960x540.

The shipped upstream script advertises 640x360 as the minimum but rejects
960x540: it requires every dimension to be a multiple of 8 although 540 is
divisible by 4, not 8. On the existing Vulkan/VideoOut implementation the
render target width retains its 8-pixel alignment and only the height
validation is relaxed to four pixels. No display or presentation dimensions
are changed. The native renderer and AHB output remain untouched.

Exact-source anchored: fail CI on upstream changes rather than silently
packaging a 540p option that the game preparation will reject.
"""
from pathlib import Path


def patch_sotc_lowres_modes(script: Path) -> None:
    source = script.read_text()
    old = (
        "    if not (640 <= w <= 7680 and 360 <= h <= 4320) or w % 8 or h % 8:\n"
        "        raise SystemExit(f'render size {size}: 640x360 to 7680x4320, multiples of 8')"
    )
    new = (
        "    # SotC Android: 540p is exactly 960x540. Width stays 8-pixel aligned;\n"
        "    # 540 is 4-pixel aligned, not 8. This does not resize the AHB output.\n"
        "    if not (640 <= w <= 7680 and 360 <= h <= 4320) or w % 8 or h % 4:\n"
        "        raise SystemExit(f'render size {size}: width multiple of 8, height multiple of 4')"
    )
    if source.count(old) != 1:
        raise ValueError("SotC low-resolution patch rejected: unknown upstream render validator")
    if source.count("def render_patches(elf, ph, size):") != 1 or \
       source.count("RENDER_SITES = [") != 1 or \
       source.count("return writes") < 1:
        raise ValueError("SotC low-resolution patch rejected: render-site mapping changed")
    script.write_text(source.replace(old, new))
    print("SotC render-size validation patched: exact 960x540 and 640x360, "
          "8px-aligned width / 4px-aligned height; PS4 720p output unchanged")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--script", type=Path, required=True)
    patch_sotc_lowres_modes(p.parse_args().script)
