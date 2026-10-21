#!/usr/bin/env python3
"""Analyze matched Snapdragon GSR2 GPU readbacks in android-game.log.

Only compare GSR_STAGE_SRGB pixels from the SAME GSR2 dispatch generation.
Raw RGBA16F values are linear light; comparing them directly with guest sRGB
bytes was a false darkness diagnosis in the 2.1.7 native-AA investigation.
The 32x18 thumbnails provide stage/quadrant localization, NOT a reference
PSNR metric or a proof that GSR2 reconstructs temporal detail correctly.
"""
import argparse
import json
import re
from pathlib import Path

SAMPLE = re.compile(
    r"^GSR_STAGE_SRGB stage=(\w+) y=(\d{2}) rgb=([0-9A-Fa-f]{192}) generation=(\d+)$"
)
STAGES = ("scene_proxy", "gsr2_output", "ui_blit", "display_final")
PAIRS = tuple(zip(STAGES[:-1], STAGES[1:]))


def parse_log(log: str) -> dict[int, dict[str, list]]:
    raw = {}
    for line in log.splitlines():
        match = SAMPLE.match(line.strip())
        if not match:
            continue
        name, y, hexdata, generation = match.groups()
        if name not in STAGES:
            continue
        gen = int(generation)
        row = int(y)
        group = raw.setdefault(gen, {}).setdefault(name, {})
        # In a double-present (or a repeated capture), the first complete
        # set is used: do not splice two images for the same stage/frame.
        group.setdefault(row, [
            tuple(int(hexdata[n+i:n+i+2], 16) for i in (0, 2, 4))
            for n in range(0, 192, 6)
        ])
    return {
        generation: {
            name: [by_row[y] for y in range(18)]
            for name, by_row in images.items()
            if len(by_row) == 18 and set(by_row) == set(range(18))
        }
        for generation, images in raw.items()
    }


def compare(a: list, b: list) -> dict:
    totals = [0, 0, 0, 0]
    count = [0, 0, 0, 0]
    max_abs = 0
    high_diff = 0
    for y in range(18):
        for x in range(32):
            q = (y // 9) * 2 + (x // 16)
            for c in range(3):
                d = abs(a[y][x][c] - b[y][x][c])
                totals[q] += d
                count[q] += 1
                max_abs = max(max_abs, d)
                high_diff += d >= 64
    return {
        "mean_abs_rgb": round(sum(totals) / sum(count), 3),
        "quadrant_mean_abs_rgb": [round(t / n, 3) for t, n in zip(totals, count)],
        "max_abs_channel": max_abs,
        "channels_with_abs_difference_ge_64": high_diff,
    }


def report(frames: dict, generation: int) -> dict:
    data = frames.get(generation, {})
    diff = {}
    for a, b in PAIRS:
        if a in data and b in data:
            diff[f"{a}_to_{b}"] = compare(data[a], data[b])
    return {
        "generation": generation,
        "domain": "display-equivalent sRGB (not raw FP16 linear)",
        "stages_present": [s for s in STAGES if s in data],
        "stages_missing": [s for s in STAGES if s not in data],
        "all_stages_matched_generation": all(s in data for s in STAGES),
        "differences": diff,
        "note": (
            "Large scene->GSR2 differences can reflect sharpening or history; "
            "UI may add text. This is stage localization, not a correctness verdict."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path, help="android-game.log or extracted ZIP log")
    parser.add_argument("--generation", type=int, default=None)
    args = parser.parse_args()
    frames = parse_log(args.log.read_text(encoding="utf-8", errors="replace"))
    if not frames:
        print(json.dumps({"error": "No generation-tagged GSR_STAGE_SRGB grids. "
                                  "Use the instrumented GSR2 branch and GOW3_GSR2_AUTO_PROBE=1."}))
        return 2
    if args.generation is None:
        complete = [gen for gen, data in frames.items() if all(s in data for s in STAGES)]
        generation = max(complete if complete else frames)
    else:
        generation = args.generation
    print(json.dumps(report(frames, generation), indent=2))
    return 0 if generation in frames else 2


if __name__ == "__main__":
    raise SystemExit(main())
