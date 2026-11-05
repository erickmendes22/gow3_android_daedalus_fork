# Bachata S4+ core 025 — GoW III Android integration baseline

## Verified source state (2026-10-15)

- Public ARM64 Bachata-related repository: https://github.com/zenithblue-oss/shadps4-arm64
- Only advertised branch: `main` at `be6bc2e9c60799e071dd2fafa6216e8d80ec619c`. The last source-code commit preceding the hardening commit is dated **2026-08-27**; the repository was pushed 2026-08-28.
- Its pinned FEX is `f2b679f6028ce1c38875233aecfcf5d3f8ebecec`, dated **2026-07-12**.
- GoW III Port's pinned FEX in `third_party/FEX` is `fb925d6fc5cc8576bf0f9ae6978fc6d912485593`, dated **2026-10-12**.
- These public sources do **not** establish that the tagged BACHATA S4+ **core 025 runtime binary** was compiled from the exact `zenithblue-oss/main` commit. The runtime's own build/source SHA must be compared to certify that. Do not label `main` "latest core 025" until verified.

## Architectural comparison

| Subsystem | ARM64 Bachata source | GoW III Port |
| --- | --- | --- |
| Guest FEX | Integrated shadPS4 guest CPU, pinned July FEX | Separate native `libgow3cpu.so` and CPU bridge, pinned October FEX |
| Vulkan draw | `src/video_core/renderer_vulkan/vk_rasterizer.cpp`; no GoW III speculative draw pipeline | `gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp` with optional draw pipeline, per-draw preparation, and recording threads |
| Shader pipeline compilation | Synchronous graphics-pipeline creation in the inspected `vk_pipeline_cache.cpp` | Multiple async compilation/capture workers, background warmup |
| GPU timeline | `vk_scheduler.cpp` avoids querying the Vulkan timeline semaphore for every submission | GoW III scheduler already batches reads and polls its cached timeline after 32 checks |
| Readback | Ordinary texture-cache downloads via deferred priority operations | GoW III demand/deferred readbacks with pending size/count budgets and optional stale CPU views |
| FSR | The inspected public Bachata core does not include GoW III's temporal scene/HUD hooks | GoW III-specific upscaler, patch inputs, depth, camera capture, guest display composition |

A whole-directory replacement of `gpu/shadps4` with `src/video_core` would remove or break GoW III's FSR, resolution, patch, draw-prep, custom runtime and presentation glue. The public baseline is **older** in several upstream components. Pin it as the reference and port *proven compatible* renderer improvements individually; preserve the newer FEX, scheduler optimizations and game-specific changes.

## Changes in this isolated branch (no CI trigger)

- On Android only, limit asynchronous shader compilation to two workers and capture to one worker; never elevate speculative shader capture above the game.
- On Android only, default the speculative draw pipeline off to reproduce a less contended direct Vulkan command path, while leaving all desktop behavior unchanged.
- Existing `GOW3_DRAW_PIPE=1` opts back into the port's parallel draw pipeline; `GOW3_GPU_COMPILER_WORKERS=1..6` tests another worker budget.
- FEX JIT dynamic L1 was already set to a fixed cache by default in this feature branch; `GOW3_FEX_DYNAMIC_L1=1` is an explicit rollback. TSO is not weakened.
- Expensive camera matrix scanning is skipped when the upscaler is inactive, and scanning is capped per frame.

## Performance verification still required

A/B on the **same** CUSA01715 version, save position, camera location, scene input resolution, output resolution, patch set, temperature, refresh, driver, JIT warmup, and FSR state. Compare median FPS and 1% lows with:
1. Android low-contention baseline (draw pipe off; two compiler workers).
2. Previous port-style draw pipeline (`GOW3_DRAW_PIPE=1`) at the same worker count.
3. Original compilation budget (`GOW3_GPU_COMPILER_WORKERS=4`) with draw pipe controlled.
4. FEX `GOW3_FEX_DYNAMIC_L1=1` versus 0, changing **only** one parameter per measurement.

These are reasoned workload mitigations, **not validated FPS improvements**. A GPU trace or `GOW3_FRAME_STATS` is required to confirm whether shader preparation, guest FEX, texture readback, Vulkan present or queue drains dominates in the actual GoW III scene.
