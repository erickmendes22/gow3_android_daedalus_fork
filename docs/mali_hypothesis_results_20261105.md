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
