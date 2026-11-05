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

# GSR2 exposes cumulative history outcomes every 600 dispatches. Keep the
# intervals separate: a run may contain thousands of validated temporal
# frames before the camera feed disappears after a scene transition.
HISTORY = re.compile(
    r"^GSR2_HISTORY_GUARD dispatch=(\d+) valid=(\d+) missing=(\d+) "
    r"shader=(\d+) projection=(\d+) position=(\d+) rotation=(\d+)$"
)
CAMERA_VERIFIED = re.compile(r"GOW3_CAMERA_VERIFIED_VP\b")


def parse_temporal_history(log: str) -> dict:
    entries = []
    for line in log.splitlines():
        m = HISTORY.search(line.strip())
        if m:
            dispatch, valid, missing, shader, projection, position, rotation = map(int, m.groups())
            entries.append({
                "dispatch": dispatch, "valid": valid, "missing_camera": missing,
                "different_shader": shader, "projection_cut": projection,
                "position_cut": position, "rotation_cut": rotation,
            })
    # Some log packs repeat the same run in more than one file. The last
    # cumulative sample is authoritative for a continuous session.
    entries.sort(key=lambda row: row["dispatch"])
    interval = []
    previous = None
    for current in entries:
        if previous and current["dispatch"] <= previous["dispatch"]:
            previous = current
            continue
        if previous:
            delta_dispatch = current["dispatch"] - previous["dispatch"]
            delta_valid = current["valid"] - previous["valid"]
            delta_missing = current["missing_camera"] - previous["missing_camera"]
            if 0 <= delta_valid <= delta_dispatch and delta_missing >= 0:
                interval.append({
                    "from_dispatch": previous["dispatch"],
                    "to_dispatch": current["dispatch"],
                    "valid": delta_valid, "missing_camera": delta_missing,
                    "valid_fraction": round(delta_valid / delta_dispatch, 4),
                })
        previous = current
    latest = entries[-1] if entries else None
    return {
        "camera_verified_log_entries": len(CAMERA_VERIFIED.findall(log)),
        "samples": len(entries),
        "latest_cumulative": latest,
        "intervals": interval,
        "latest_valid_fraction": interval[-1]["valid_fraction"] if interval else None,
        "temporal_dropout_intervals": [
            {"from_dispatch": row["from_dispatch"], "to_dispatch": row["to_dispatch"]}
            for i, row in enumerate(interval) if row["valid"] == 0 and
            any(older["valid_fraction"] >= 0.5 for older in interval[:i])
        ],
        "interpretation": (
            "Valid history can be intermittent or disappear during menus and scene "
            "transitions; counts alone do not prove broken camera recovery in gameplay."
        ),
    }



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
    log_text = args.log.read_text(encoding="utf-8", errors="replace")
    frames = parse_log(log_text)
    history = parse_temporal_history(log_text)
    if not frames:
        if history["samples"]:
            print(json.dumps({"stage_grids": "not present (use the GSR2 stage diagnostic build)",
                              "history": history}, indent=2))
            return 0
        print(json.dumps({"error": "No temporal history counters or generation-tagged "
                                  "GSR_STAGE_SRGB grids. Use the 2.1.7 GSR2 diagnostics build."}))
        return 2
    if args.generation is None:
        complete = [gen for gen, data in frames.items() if all(s in data for s in STAGES)]
        generation = max(complete if complete else frames)
    else:
        generation = args.generation
    print(json.dumps({"stages": report(frames, generation), "history": history}, indent=2))
    return 0 if generation in frames else 2


if __name__ == "__main__":
    raise SystemExit(main())
