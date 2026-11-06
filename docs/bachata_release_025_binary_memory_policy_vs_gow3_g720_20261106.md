# Reverse engineering of Bachata S4 RELEASE 0.2.5 binary: G720 memory-policy decision

Source: exact Library APK `bachatas4-0.2.5-release.apk` (211,009,680 bytes),
SHA-256 `1df49463f396df8b6f042230bdc1bb9f948b8e69894c378915920875c40ab0ee`.

Extracted native host `libbachata_native_runtime.so`,
SHA-256 `147fd32524cbf21c8946c6e93bd6e3d50ed325251aa4acae5a284f456ce6a9f4`,
AArch64 ELF. Embedded driver `libvulkan_panfrost.so` from
`Bachata-PanVK-V3-glibc.zip`, SHA-256
`fe60e41514698e5430551adc8718e315ab16325406b1da3af44e40e615ca4af4`.

This is **the APK binary**, not the public Bachata/shadPS4 core.

## Binary facts (disassembled AArch64, addresses for this particular ELF only)

`TextureCache::GarbageCollectImages` at VA `0x37acb88`.
The function reads `Instance::GetLiveGpuMemoryBudget` in a guarded path
(vendor/driver-id check, enabled telemetry, available budget).
At `0x37acc10..0x37acc70`, it calculates approximately:

- `consideredBudget = min(liveBudget, storedBudget)`;
- `pressure = 0.4 * consideredBudget`, stored at TextureCache offset `+0x5500`;
- `critical = max(0.8 * consideredBudget, consideredBudget - 384 MiB)`,
  stored at offset `+0x5508`;
- calls `Instance::SetImageGpuMemoryTelemetryThresholds(pressure, critical)`.

Both fractions are produced with integer arithmetic, so allow rounding.
This is conditional **pressure/critical telemetry**, not a global 40% image
allocation cap, not an image-pool capacity, and not an unconditional GC
trigger of 40%.

At `0x37acd48..0x37acecc`, cleanup also consults cached free system
memory and memory usage and changes the number/age of reclaimed
images; no unconditional disabled eviction can be inferred.

The constructor `TextureCache::TextureCache` VA `0x379cd3c`
has a separate budget-derived baseline watermark calculation near
`0x379d044..0x379d0d0`, with a target of 8 GiB, 1.5/3 GiB
lower-bound constants and explicit budget headroom. The *conditional*
live-budget branch supersedes pressure/critical thresholds when active.
Do not conflate constructor fallback with PanVK runtime telemetry.

Driver package's `BACHATA-DISTRIBUTION.json` states that the kbase
GPU recycles tiler heap chunks by default. This matches the exact
source-pinned `JICA98/panvk-kbase-android` patch
`patches/bachata-v3/0007-panvk-kbase-recycle-tiler-heap-chunks-on-the-GPU-by-.patch`
at commit `2a9358a000fd691dac36d04c170fa3bd4101ff06`.
`PANVK_KBASE_SKIP_HEAP_OPS=0` by default keeps
`FINISH_FRAGMENT/FRAGMENT_COMPLETED` chunk recycling on GPU. Turning it
on switches to whole-heap renewal/drain, risking GPU stalls.
This is separate from emulator VkImage exact-match BC/RGBA pools.
The package's metadata explicitly reports G615 qualification and **V2
FPS parity**, not a tested G720 performance advantage.

## Device-specific risk analysis and decision

User log `GodOfWar3-Logs-20261106-064553.zip`:
`gc_trigger_pct=70`, `gc_pressure_pct=85`, 24 reported
`routine eviction` batches, total 701 evicted, **0 writebacks** and
**0 memory-pressure reports**. Usage roughly 78% of Vulkan moving budget.
Image pools reported BC **148 hits, 492 misses, 264 drops** and
max BC/RGBA128 allocations >400 ms.
No `DEVICE_LOST` or `VK_ERROR_OUT_OF_DEVICE_MEMORY` was present.

Porting the RELEASE's `40% pressure` literally to this G720 would
collect **earlier**, not later, than Daedalus's new 85% threshold,
counter to the observed avoidable churn. Its `max(80%,budget-384MiB)`
critical threshold may be **lower** than 95%, i.e. more conservative.
A simple percentage substitution is not equivalence because the
driver computes a different *live* memory budget, and the runtime may
route through a different branch. The Bachata driver is a distinct V3
G615-targeted build; replacing the newer experimental G720 driver
`PanVK 7e97db4d` is also unsupported by this log.

**Action:** Keep the actually justified changes in the separate experimental
Android branch: delay Daedalus GC trigger **70 -> 85%** without
changing critical **95%**, preserve the clean-first, GPU-complete
and dirty-texture guards, and test the separate exact-create BC/RGBA128
scene-retention increase 128/64 -> **192/96 MiB** (48 entries each).
The 90% VMA pool pressure guard remains unchanged.

Do **not** replace this with Bachata's more eager percentage thresholds
unless hardware A/B shows less stutter or memory pressure requires more
aggressive cleanup. It is not defensible to claim FPS improvement solely
from different watermarks. The currently largest recorded startup
bottleneck is graphics pipeline creation (~17.2s of timed events);
run twice with preserved `VK_KHR_pipeline_binary` cache before
concluding steady-FPS gain.

## Build and rollback verification

Native candidate branch:
`analysis/gow3-mali-pipeline-preflight-20261105`.
`GOW3_MALI_GC_TRIGGER_PCT=70` still restores the prior early GC;
`GOW3_MALI_SCENE_IMAGE_RETENTION=0` restores 128/64 MiB and 24 entries
while preserving base pool functionality. Leave `GOW3_PREP_WORKERS=0`
to avoid adding an unrelated variable. Stable production branch unmodified.
