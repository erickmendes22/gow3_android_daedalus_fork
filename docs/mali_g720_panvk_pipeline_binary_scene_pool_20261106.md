# G720 MC7 PanVK 7e97db4d — device log driven optimization, 2026-11-06

## Raw evidence

Source: user-provided `GodOfWar3-Logs-20261106-064553.zip`
SHA-256 `b9f1a8b6442440cd638fd27c49ab625b9627db7ca009376a46e98a5c79c5524e`.
Only `logs/android-game.log` is included; about 209 seconds over 31
`MALI_PERF_STATS` reporting intervals. Device: Poco X7 Pro, Mali-G720 MC7,
custom PanVK commit `7e97db4d`; guest CUSA01715 patch 01.02, 960×540,
VSync off, draw preparation workers=0.

```text
Pipeline binary cache: 9 hits, 247 compiled, 0 rejected, 247 saved,
0 cache errors (restore 0.379 ms, compile 64.196 ms each)
GOW3_BC_IMAGE_POOL hits=148 misses=492 stored=435 drop=264 retained_mib=13
```

Totals across intervals (stage timings are NOT additive because of nested
timers, and sample rates differ):

| Recorded stage | Count | Total time (ms) | Largest item (ms) |
|---|---:|---:|---:|
| graphics_pipeline_new | 281 | 17177.25 | 240.14 |
| shader_module_new | 515 | 1045.05 | 20.83 |
| image_bc_new | 741 | 1129.66 | 408.29 |
| image_rgba128_new | 348 | 785.65 | 429.13 |
| gpu_draw_cpu (1/256 sample) | 6427 | 245.37 | 125.69 |
| pm4_submit_wall (1/32 sample) | 1986 | 6859.54 | 527.14 |

The driver has enabled `VK_KHR_pipeline_binary`; **9 recorded hits** prove
binary restoring is operational, not that all 247 saved blobs will hit on
the following run. Expected replay is to launch twice, preserve app and cache,
traverse the identical scene, and compare hit/compile/save counters and FPS.

## Change delivered to separate-install tester branch

Only in the PanVK launcher profile,
`GOW3_MALI_SCENE_IMAGE_RETENTION=1` allows retired identical VkImages
to remain in separate larger BC and RGBA128 pools, up to 48 entries each:

| Pool | Previous | Experiment | Additional memory max |
|---|---:|---:|---:|
| BC | 128 MiB / 24 entries | 192 MiB / 48 | 64 MiB |
| RGBA128 | 64 MiB / 24 | 96 MiB / 48 | 32 MiB |
| Combined | 192 MiB | 288 MiB | **96 MiB** |

This targets BC pool turnover (264 drops) and cold scene recreation spikes,
not general steady-frame shader/GPU throughput. Existing guards remain:
- identical image format, dimensions, layout, usage, samples, tiling and allocator;
- images returned only after the scheduler's completion callback;
- VMA device-local budget must remain below 90%, otherwise the pool purges;
- old per-image entry size ceilings and Vulkan budget allocation flag unchanged;
- no modification to BC/R32 guest-memory alias `safe_to_delete` or GPU-dirty policy.

Set `GOW3_MALI_SCENE_IMAGE_RETENTION=0` to disable only the expanded pool,
without disabling existing 128 MiB BC / 64 MiB RGBA128 reuse.

`GOW3_MALI_PM4_IDLE_BACKOFF_US=20` remains included from the earlier
single-core CPU producer contention test; it was independently screened
before this log and can be disabled with 0. No FPS result from this G720 log
proves that optimization's efficacy on device yet.

**Not enabled together:** `GOW3_PREP_WORKERS=2`. This changes checksum,
dirty/replay and host CPU scheduling; existing 1/256 draw samples, some
overlapping shader-compilation waits, cannot establish it as a standalone gain.
Keep at 0 for clean A/B on BC/RGBA128 retention and test workers separately.

## Test gate for users / testers

1. Run original scene twice without clearing cache, with same 960×540 patch
   and VSync off. Compare `Pipeline binary cache` counters. Do NOT infer
   247 hits from a single prior first-run log.
2. Compare scene transitions with BC/RGBA128 retention default **1** versus
   setting **0**, one variable at a time, including frame-time spikes,
   `GOW3_BC_IMAGE_POOL` hits/misses/drop and any memory/driver failures.
3. Compare after warmup to identify steady FPS separately from first-use
   pipeline compilation; do not add stage timings across nested scopes.
4. Check correct textures and GPU-dirty aliases; do not force
   `safe_to_delete=1` simply after two frames.
5. If memory issues occur, set `GOW3_MALI_SCENE_IMAGE_RETENTION=0`, keep
   the original pool and capture logs. The production branch is untouched.

Tests: `tests/test_mali_scene_image_retention.py`, existing BC/RGBA128
VMA/alias guards, and separate-install PanVK Android native build CI.

## Follow-up: GC trigger was more restrictive than the pool limits

A review of the user's same `GodOfWar3-Logs-20261106-064553.zip` shows
`gc_trigger_pct=70`, `gc_pressure_pct=85` in the PanVK startup line.
All **24** texture-cache reports are **routine eviction**, not memory
pressure; the reported counts sum to **701 image evictions**, zero
writebacks and zero dirty-kept. Logged usage was on average approximately
**78% of the moving Vulkan memory budget**. The source uses a short
`gc_tick - 16` LRU age for routine evictions, and `gc_tick - 80` for
actual pressure, so threshold 70% systematically reclaims live reusable
working sets before the pool even has a chance to prevent new allocations.

The existing GPU cache code already permits an 85% trigger. Changed **only**
the PanVK launcher's default `GOW3_MALI_GC_TRIGGER_PCT=70` to **85**,
aligning routine GC start to the existing 85% pressure watermark and
keeping the separate **95% critical watermark**. Explicit `=70` remains
available for A/B. No GPU-dirty alias deletion rule was changed.

**Public Bachata core comparison:** `zenithblue-oss/shadps4-arm64`,
`src/video_core/texture_cache/texture_cache.h/.cpp` has no equivalent
BC/RGBA128 recycled VkImage pools or matching pool-size cap.
It computes GC watermarks from the Vulkan device-local budget with
`DEFAULT_PRESSURE_GC_MEMORY=1.5 GiB`,
`DEFAULT_CRITICAL_GC_MEMORY=3 GiB`,
`TARGET_GC_THRESHOLD=8 GiB` and different LRU rules. Those are
**watermarks**, not 1.5/3 GiB allocation or image-pool hard limits. The
Bachata pressure watermark can be lower than Daedalus's 85%; the
strategies cannot be ranked by comparing one percentage.

This GC change targets texture churn rather than shader compilation.
It **does not establish a quantified FPS gain**. Test the same scene
after warming VK_KHR_pipeline_binary with A/B `GOW3_MALI_GC_TRIGGER_PCT=70`
versus `=85`, pool-expansion toggle held fixed, and compare evictions,
allocation latency, actual frame time and memory stability.
