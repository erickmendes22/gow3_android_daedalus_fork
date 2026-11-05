#!/usr/bin/env python3
"""CPU-only A/B performance preflight, run BEFORE any GoW3 native/APK build.

Do not describe this as measured Mali FPS. It exercises an isolated model of the
image-free descriptor path. The draw/frame conversion is grounded in previously
captured G615 game telemetry, assumes EVERY draw is affected (optimistic), and
rejects changes clearly too small to matter. No APK is produced on gate failure.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / 'fixtures' / 'mali_g615_20261105_152530.json'
SOURCE = HERE / 'mali_image_free_bind_bench.cpp'


def estimate_ms_per_frame(delta_ns_per_draw, draws_per_frame, affected_fraction=1.0):
    """Best-case synthetic conversion, not device frame-time measurement."""
    if not (0 <= affected_fraction <= 1):
        raise ValueError('affected fraction outside 0..1')
    if draws_per_frame <= 0:
        raise ValueError('draws/frame must be positive')
    return max(0.0, delta_ns_per_draw) * draws_per_frame * affected_fraction / 1e6


def decide(bench, fixture, minimum_ms=None):
    min_ms = fixture['min_meaningful_ms_per_frame'] if minimum_ms is None else minimum_ms
    saving = estimate_ms_per_frame(bench['delta_ns_per_draw'], fixture['draws_per_frame_est'])
    budget = fixture['non_pipeline_draw_cpu_ms_per_frame_est']
    if not 0 < min_ms <= budget:
        raise ValueError('target ms/frame must fit the measured draw-CPU budget')
    if saving > budget:
        raise ValueError('synthetic gain exceeds measured total non-pipeline draw CPU budget')
    return saving >= min_ms, saving, min_ms


def run_bench(iterations=1000000):
    compiler = os.environ.get('CXX', 'c++')
    with tempfile.TemporaryDirectory(prefix='gow3-mali-perf-') as tmp:
        binary = Path(tmp) / 'benchmark'
        subprocess.run([compiler, '-std=c++20', '-O3', '-Wall', '-Wextra',
                        '-Werror', str(SOURCE), '-o', str(binary)], check=True)
        output = subprocess.check_output([str(binary), str(iterations)], text=True)
    data = json.loads(output)
    if data.get('kind') != 'synthetic_image_free_bind_only' or data.get('samples', 0) < 7:
        raise ValueError('unexpected or insufficient A/B samples')
    if min(data['baseline_ns_per_draw'], data['candidate_ns_per_draw']) <= 0:
        raise ValueError('invalid nanosecond timings')
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report-only', action='store_true',
                        help='Print result but do not block; CI APK builds MUST NOT use this')
    parser.add_argument('--fixture', type=Path, default=FIXTURE)
    parser.add_argument('--iterations', type=int, default=1000000)
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text())
    if fixture['sampling_draw_one_in'] != 256 or fixture['sampling_prepare_one_in'] != 32:
        raise ValueError('sampling denominators differ from vk_mali_perf_stats.h')
    print('SOURCE:', fixture['source_log'], fixture['source_sha256'])
    print('DEVICE:', fixture['device'], fixture['resolution'])
    print('STEADY:', fixture['draws_per_frame_est'], 'draws/frame estimated; '
          f"{fixture['non_pipeline_draw_cpu_ms_per_frame_est']:.2f} ms/frame non-pipeline Draw CPU")
    result = run_bench(args.iterations)
    passed, saving, threshold = decide(result, fixture)
    print('HOST SYNTHETIC A/B:',
          f"old={result['baseline_ns_per_draw']:.3f}ns/draw",
          f"new={result['candidate_ns_per_draw']:.3f}ns/draw",
          f"delta={result['delta_ns_per_draw']:.3f}ns/draw")
    print('OPTIMISTIC MODEL:', f'{saving:.6f} ms/frame',
          f'(assumes 100% of {fixture["draws_per_frame_est"]:.0f} draws affected)')
    print('GATE:', 'PASS' if passed else 'BLOCK APK',
          f'(minimum {threshold:.1f}ms/frame)')
    print('LIMITATION: Synthetic host model; NOT measured Mali execution, FPS or full BindTextures.')
    print('LIMITATION: The texture helper is disabled by default; its Fork/Join saving is 0 ms.')
    return 0 if args.report_only or passed else 2


if __name__ == '__main__':
    raise SystemExit(main())
