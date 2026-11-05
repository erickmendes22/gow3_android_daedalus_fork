# GoW3 Android Mali — Tested optimization hypotheses (2026-11-05)

**Scope:** Analysis branch only. No APK produced; no production renderer code changed.
Production branch: fix/gow3-218-panvk-videoout-label-retire-20261031.

## Grounded observations

- G615 MC6 at 1280x720: previous session measured ~7.0–7.4 steady FPS, including intervals without new pipelines or image allocations.
- Existing checked-in fixture from GodOfWar3-Logs-20261105-152530.zip: sampled Rasterizer::Draw CPU 22.38 ms/frame, of which pipeline lookup 7.56 ms/frame and all other draw CPU 14.82 ms/frame.
- Mali G720 is a separate run, with graphics_pipeline_new=109/4347.10/39.88/57.98; this explains potential stutter spikes, not the G615 no-compile steady FPS.
- Draw CPU samples are estimated wall-clock host work. GPU stages and true critical path have not been measured in the G615 capture.

## GitHub Actions tests (2026-11-05)

1. Image-free draws: existing true A/B *host synthetic* microbench repeated; old 3.017 ns/draw, new 2.181 ns/draw; optimistic 0.000386 ms/frame using 462 draws/frame. REJECT: negligible, 10 ms/frame build gate blocks APK.
2. Pipeline cache lifecycle: added actual Vulkan (host driver) compute pipeline test. Distinct live and worker caches compile successfully, worker-to-live merge and snapshot restore work, and private-worker pre-seeding can be executed. The host llvmpipe driver serializes 32 bytes (header only, has_cache_payload=0); no evidence of actual compiled shader reuse or PanVK speedup. Do not promote this to an APK.
3. Frame budget: added four Python tests and explicit theoretical upper bounds for saving an entire stage on the frame's critical path. At 7.4 FPS:

| Removed stage | Entire stage ms/frame | Theoretical maximum FPS | Max gain |
|---|---:|---:|---:|
| Pipeline lookup | 7.56 | 7.839 | 5.93% |
| Other Draw CPU | 14.82 | 8.312 | 12.32% |
| All sampled Draw CPU | 22.38 | 8.869 | 19.85% |

To gain 25% at 7.4 FPS requires at least 27.03 ms/frame of critical-path savings. The entire sampled Draw CPU work is only 22.38 ms/frame, so CPU draw micro-optimizations cannot on their own explain or solve the sustained 7 FPS problem. The above are optimistic mathematical upper bounds, NOT predicted FPS improvements.

## Decisions

- Discard image-free texture bookkeeping optimization; no APK.
- Keep pipeline cache warmup as separate cold-stutter research; do not claim it fixes steady FPS.
- Do not add speculative pipeline worker-cache seeding in production: host driver gives no compiled cache payload and current test does not demonstrate gains on PanVK.
- Next high-impact issue is attributing the remaining ~135 ms/frame. The renderer already has an optional Vulkan timestamp profiler in gpu/shadps4/video_core/renderer_vulkan/vk_gpu_profiler.cpp (GOW3_GPU_PROFILE=1), but GPU execution timing is missing for these G615 logs. Need correlated FEX/PM4, Vulkan queue GPU timestamps, and VideoOut waits before a claim of a substantial steady-state FPS optimization.
- Preserve existing 10 ms/frame synthetic gate on APK production branch.

## Reproduction

Run the test workflow:
https://github.com/erickmendes22/gow3_android_daedalus_fork/actions/runs/42016088828

Relevant files:
- benchmarks/mali_pipeline_cache_lifecycle.cpp
- benchmarks/mali_frame_budget_gate.py
- tests/test_mali_frame_budget_gate.py
- benchmarks/mali_draw_perf_gate.py
- .github/workflows/gow3-mali-pipeline-preflight.yml

This test environment uses llvmpipe graphics software on an x86 CI runner and does not benchmark Mali GPU hardware or GoW3 Vulkan graphics pipelines.

## 2026-11-05 follow-up: real source PM4 and copy-pool tests

### PM4 register checksum condition (correctness)

Production previously tested whether the `DrawPreparation*` object existed,
even when `DrawPreparation::Enabled()` was false because no preparation
workers were running. Its register-packet hash was therefore still computed
without a consumer on Mali with `GOW3_PREP_WORKERS=0`.

The analysis-branch correction changes the guard to
`(draw_prep && draw_prep->Enabled()) || force_checksum` while preserving
the explicit `GOW3_PM4_CHECKSUM_ALWAYS` rollback.

A native host benchmark compiles the exact `Liverpool::HashRegisterPacket`
body extracted from the project's source. At 64 words/packet, savings were
approximately 90-120 ns/packet on the Actions x86 host. At that rate,
saving 10 ms/frame would require about 83,000-109,000 such packets per frame.
The G615 fixture does not include measured packet counts; **do not claim a
material device FPS gain from this correction alone**. The legacy checksum
and dirty-register tests are included in the no-APK CI.

### Copy-pool wait: actual synchronization change and two workload controls

In the original `gpu/shim/gow3_copy.cpp`,
`Gow3Copy::WaitAsync()` called `Pool::WaitAll()`: this waited until
**all** globally pending copies finished, even copies enqueued on another
producer thread **after** the barrier. A GPU submission only needs the
prefix issued before its barrier.

The analysis branch implements `Pool::WaitIssued()`, which:
- Under the existing pool mutex, closes the issued prefix as an epoch;
- Helps execute only queued tasks whose epoch belongs to the required prefix;
- Awaits a release/acquire `retired_epoch` watermark, published by `Complete`
  **after** all callbacks for retired epochs run;
- Does not wait for unrelated future copies or allocate a callback per wait;
- Leaves `AfterCopies` callback ordering and `GOW3_COPY_THREADS` unchanged.

The regression benchmark extracts and compiles the **real Pool class** twice:
the original source from production commit `0f919000` and the candidate
branch's source. Results on the GitHub Actions x86 host:

| Scenario | Original | Candidate | Meaning |
|---|---:|---:|---|
| Deliberately overlapping **late producer** | 236.142 ms | 45.032 ms | 191.110 ms less waiting; prefix and callback order verified |
| Ordinary one-copy barrier | 2.147 µs | 2.150 µs | No meaningful normal-path regression in this run |
| Empty barrier | 13.844 ns | 9.270 ns | No added empty-barrier overhead in this run |

These are controlled host tests, not GoW3 game FPS tests. A late concurrent
producer is **required** for the large 191 ms benefit; its frequency and
critical-path contribution have not been established in the G615 device logs.
The existence of multiple copy-issuing call sites in `buffer_cache.cpp`
proves this scenario is possible, not common or costly in real gameplay.

**Decision:** Keep both code changes isolated in
`analysis/gow3-mali-pipeline-preflight-20261105`. Do not generate an APK
or claim an FPS uplift until device evidence attributes significant recurring
wait time to the copy-pool's later tasks. The original native/APK production
branch is unchanged, and the 10 ms/frame gate remains intact.

Copy-pool and PM4 test run (no APK):
https://github.com/erickmendes22/gow3_android_daedalus_fork/actions/runs/42019263894
