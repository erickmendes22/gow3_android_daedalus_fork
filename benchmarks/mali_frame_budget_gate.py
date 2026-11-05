#!/usr/bin/env python3
"""Optimistic GoW3 G615 steady-state frame budget, not a benchmark of the GPU.

Uses the previously captured 720p G615 draw CPU fixture. A stage's entire
observed elapsed time is assumed to be on the frame's critical path: removing
it gives a best-case FPS ceiling, not an expected FPS improvement. Overlap with
GPU execution, other threads or waits can make real gains strictly smaller.
"""
import argparse
import json
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures/mali_g615_20261105_152530.json"


def budget(base_fps: float, stage_ms: float):
    if base_fps <= 0:
        raise ValueError("baseline FPS must be positive")
    baseline_ms = 1000.0 / base_fps
    if stage_ms < 0 or stage_ms >= baseline_ms:
        raise ValueError("stage elapsed time is out of range")
    fastest = 1000.0 / (baseline_ms - stage_ms)
    return {
        "baseline_frame_ms": baseline_ms,
        "max_fps": fastest,
        "max_gain_percent": 100.0 * (fastest / base_fps - 1.0),
    }


def required_ms(base_fps: float, target_percent: float):
    if base_fps <= 0 or target_percent <= 0:
        raise ValueError("FPS and target increase must be positive")
    return (1000.0 / base_fps) * (1.0 - 1.0 / (1.0 + target_percent / 100.0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fps", type=float, default=7.4,
                        help="Observed G615 steady-state FPS from prior log; change for another run")
    args = parser.parse_args()
    fixture = json.loads(FIXTURE.read_text())
    print("GOw3 MALi FRAME BUDGET (CPU-only optimistic bounds; not measured FPS)")
    print("log:", fixture["source_log"], "device:", fixture["device"], "fps:", args.fps)
    stages = (
        ("pipeline_lookup", fixture["pipeline_lookup_ms_per_frame_est"]),
        ("non_pipeline_draw_cpu", fixture["non_pipeline_draw_cpu_ms_per_frame_est"]),
        ("all_sampled_draw_cpu", fixture["draw_cpu_ms_per_frame_est"]),
        ("rejected_image_free_bookkeeping", 0.000430),
    )
    for name, elapsed in stages:
        stats = budget(args.fps, elapsed)
        print(f"{name} cost={elapsed:.6f}ms/frame optimistic_max={stats['max_fps']:.3f}fps "
              f"optimistic_gain={stats['max_gain_percent']:.2f}%")
    for pct in (10, 20, 25):
        print(f"required_for_{pct}pct_gain={required_ms(args.fps, pct):.3f}ms/frame")
    print("LIMITATION: Sample-based draw costs, GPU execution and FEX/PM4/VideoOut not measured; "
          "a CPU-stage saving may overlap GPU work. Ceiling is not evidence of a real gain.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
