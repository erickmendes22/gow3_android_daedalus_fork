# GoW III G720 — 2026-11-13 three-log attribution (960×540 / 1280×720)

## Sources and guardrails
Device logs: `GodOfWar3-Logs-20261112-225735.zip`, `GodOfWar3-Logs-20261113-101023.zip`,
`GodOfWar3-Logs-20261113-143248.zip`. Reference: `GodOfWar3-Logs-20261112-183427.zip`.
The user-provided `feedback.txt` is a proposal, not an authoritative profiler; assumptions
were verified below against logs and current repository code. Do not compare scene FPS
across different draw counts or infer GPU occupancy solely from CPU wait percentages.

## Observed facts
- All uploads select imported `0c61ef0cdd5c9314…`, corresponding to PanVK 26.3.1.
  There is **no paired PanVK V3.2 run** in these samples.
- 2026-11-12 18:34, 1280×720: 3.7–5.7 FPS in 2536–3047 draws/frame.
  Up to 453.13 ms Vulkan image allocation; 26 texture-sync downloads took 642.37 ms
  in one seven-second window. One stall spent 340.3 ms in GC.
- 2026-11-12 22:57, 1280×720: 13.2–13.5 FPS at 295–432 draws/frame
  (capture ends before a >2000-draw comparable scene).
- 2026-11-13 10:10, 1280×720: 9.6–11.2 FPS at 402–737 draws/frame;
  a 1418.1 ms worst-frame stall includes 1125.6 ms of compiling 139 shaders/pipelines,
  while the slowest logged image allocation is 79.29 ms.
- 2026-11-13 14:32, 960×540: 4.5 FPS at 2975 draws/frame;
  11 windows with >2000 draws/frame and **zero** compiles average
  5.27 FPS with 2567 draws/frame and 82.1% CPU blocked on GPU ticks.
  The driver/VMA also reports 402.93 ms for an R32G32B32A32Uint 4096×208 image
  (13,631,488 bytes), 248.39 ms for R8Unorm 1920×1080, and multiple >140 ms ETC2 allocations.
- 14:32 starts by clearing 1337 shader blobs when `gow3-cache-schema.bin`
  is missing (`meta=8 binary=7 key=5`). The current code intentionally resets
  old v7 Boost-pointer-serialized metadata, then writes the matching schema.
  **Only one reset is evidenced**: do not bypass the schema guard without binary
  compatibility validation, or assert it repeats on every boot.
- No `GOW3_MALI_GC_BATCH` output or texture pressure report in the 14:32
  capture: **this session does not evaluate the new batched GC path**.

## Recommendations from feedback.txt that need correction
- `deferred=off` is **GOW3_DEFERRED_READBACK=0**, not deferred Vulkan image creation.
  Enabling it is a texture-visibility experiment, not a way to hide vkCreateImage.
- `vma_block_mib=0` uses VMA's default, which is ~256 MiB in the original
  large-heap allocator. Setting 256 MiB is not an improvement. 16/32/64/128
  are already accepted *opt-in* on Mali via `GOW3_MALI_VMA_BLOCK_MIB`; changing
  the default without same-save timing and RAM proof would be speculative.
- 22,000 `gfx_pipeline_binds` are aggregate counters for a sampling window,
  **not per-frame binds**. Pipeline and vertex-input bind caching already
  skips most redundant calls in heavy scenes.
- `miss_incompatible` means a non-identical VkImageCreateInfo, which cannot
  safely reuse the old Vulkan image handle. A VkImage's extent is immutable;
  "resize in place" is not a valid Vulkan optimization. Existing VMA memory
  rebind is separately guarded by requirements and completed GPU ticks.
- BC/ETC2 pool retention peaks at only ~7–51 MiB while the limit is 256 MiB.
  Increasing the limit to 512 MiB cannot resolve the observed incompatible
  shape keys, and disk conversion using the eboot preparer cannot directly
  access arbitrary GPU textures stored in installed game archives.
- More draw-preparation workers and deeper GPU submission queues were
  already tested together with a regression in prior G720 matched-driver runs;
  keep known stable 0 workers / 2 in-flight until isolated evidence says otherwise.

## Applied follow-up (non-speculative)
`vk_instance.cpp` on experimental branch now wraps the **same** Vulkan
functions used by VMA on Mali only, emitting `GOW3_MALI_VMA_DRIVER_CALL`
for >5 ms driver calls: `vkCreateImage`, `vkAllocateMemory`,
`vkBindImageMemory`, `vkBindImageMemory2`, and both image memory
requirements APIs. It does not split the allocation, change VMA's
algorithm, touch image aliases, or enable deferred readbacks.
`GOW3_MALI_VMA_CALL_TRACE=0` restores the prior VMA function table.
Correlate these entries with existing `GOW3_MALI_SLOW_IMAGE_ALLOC`
to determine whether the 403 ms is inside PanVK create, memory
allocation/bind, or VMA's internal work. A driver CPU stall is
not automatically a GPU shader bottleneck.

## Acceptance gate
1. Compile and validate native ARM64 with the new tracing.
2. A separate diagnostic APK, not a release promotion, may be built to
   collect these stage-attributed logs in the same 960×540 heavy scene.
3. Compare PanVK 26.3.1 with bundled PanVK 3.2 at the **same scene and resolution**.
4. Only change VMA block size / image pool or shader scheduling after the
   Vk API breakdown and pass GPU timing support an actual reduction.
