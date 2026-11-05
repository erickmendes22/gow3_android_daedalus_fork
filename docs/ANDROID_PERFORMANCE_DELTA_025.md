# God of War III Android — residual performance gap versus BACHATA core 025

## What is supported by code and the available log

This is a source-code investigation, **not** a claim of measured FPS gain on the Redmagic 10 Pro. The available `android-game(9).log` is from a previous revision (the former temporal-rendering path and six-worker shader warm-up still enabled), and does not benchmark the newest APK or BACHATA under matched conditions.

### 1. Speculative GPU draw preparation ran when the Android draw pipeline was disabled

- `vk_rasterizer.cpp::DrawPipeWanted()` defaults to `false` with `GOW3_ANDROID_PORT=1`.
- However, `vk_rasterizer.cpp` **unconditionally** constructed `DrawPreparation`, whose old `DefaultWorkerCount()` started half the hardware threads plus a scanner. On an 8-thread phone that is **four workers plus one scanner**. The old log explicitly reports four workers.
- Command-buffer copying, register scanning, and speculative shader input preparation may occur independently of draw-pipeline recording. A CPU-limited port can lose throughput even with background/idle-priority threads because the submit path still produces the work.
- **Branch change:** Android now chooses zero preparation workers unless `GOW3_PREP_WORKERS` is explicitly configured. The class already has a clean `Enabled()==false` path: `Build()` returns empty and the ordinary Vulkan draw path uses descriptors calculated on demand.
- Desktop behavior is unchanged. `GOW3_PREP_WORKERS=4` is the comparison/rollback to the old Android worker count; `GOW3_PREP_WORKERS=0` forces the new policy.

### 2. A forced wait every frame limited CPU/GPU overlap

- `vk_presenter.cpp::PrepareFrame()` calls `draw_scheduler.Wait(tick)` whenever the backlog exceeds `Gow3Settings::Get().frames_queued`.
- Previously Android exposed **1** as the default. A single in-flight frame can limit overlap between guest FEX JIT, Vulkan command generation and rendering.
- **Branch change:** the default Android `gow3.ini` and launcher are set to **2** frames queued. `scripts/launch_env.py` migrates existing configurations only if the key is absent; explicit choices **1, 2 or 0** remain untouched.
- This may improve throughput when GPU and CPU alternate waiting. It may add up to one frame of input latency; selecting **1** restores the previous latency-oriented policy. Do not use 0/unbounded as an unconditional performance setting, because it can increase burstiness and memory pressure.

### 3. Other examined differences that should NOT be patched blindly

- **FEX:** `cpu/guest_cpu_fex.cpp` uses a native embedded FEX core; `src/runtime_thread.c` records guest priority and affinity but does **not** map them onto an Android host scheduler. This can affect fairness with guest and Vulkan threads, but making priorities real-time or forcing CPU affinity without a measured workload risks starvation and regressions. No unsafe host-priority change was made.
- **Readbacks:** `texture_cache.cpp` has deferred/stale GPU-to-CPU downloads; `ResolveReadbacks` may still require `scheduler.Wait(tick)` and `ProcessDownloadImages` can invoke `scheduler.Finish()` on budget pressure. The core already supports `GOW3_FRAME_STATS` and readback profiling. No reduction of correctness-sensitive readback limits was made without evidence.
- **Presentation:** `vk_presenter.cpp::GetRenderFrame()` waits on presentation fences; `vk_swapchain.cpp` uses FIFO VSync when enabled. These are real possible throughput caps but require matched display/refresh, and bypassing fences is unsafe.
- **Vblank:** old `android-game(9).log` used **240 Hz**. `driver.cpp` runs a vblank-paced flip loop at the selected frequency. This raises callback/wakeup frequency versus 60/120 Hz but is not proof of the observed FPS gap; high-refresh settings must not be changed without a matched test.
- **GPU shader compilation:** the newer port already limits Android compilation to two workers and capture to one; it would be a regression to re-enable all six speculative workers by default.
- **Temporal rendering:** disabled by current Android config. No new upscale passes or shader work introduced by this branch.

## Verification

Use the same CUSA01715 01.02 build and save, same camera viewpoint/scene, device temperature, resolution, Turnip, FPS/vblank and controller input with the BACHATA and Port. Compare median FPS, 1% lows and frame time—not time elapsed in a cutscene.

Run matched A/B comparisons of exactly one variable:
1. `GOW3_PREP_WORKERS=0` vs `GOW3_PREP_WORKERS=4`, draw pipeline off.
2. `frames_queued=1` vs `frames_queued=2` on identical scene and thermal state.
3. If still CPU-limited, inspect existing counters with `GOW3_FRAME_STATS=1` only for a brief controlled diagnostic; it reports GPU command thread work, wait fraction, shader compilation and memory faults. Use `GOW3_GPU_PROFILE=1` only when GPU timing is required. **Do not enable verbose logging as a normal startup policy.**

No new APK build was triggered from this investigation branch. Changes should be merged only after build tests and device validation.
