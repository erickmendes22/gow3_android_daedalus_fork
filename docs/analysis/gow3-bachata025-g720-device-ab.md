# GoW III Mali-G720: Bachata S4 0.2.5 driver A/B (experimental)
Source: JICA98/panvk-kbase-android at 2a9358a000fd691dac36d04c170fa3bd4101ff06,
based on Mesa 5a07217f034b3e50d8c7c7794f97a2df1742613b.
Eight extra Bachata V3 patches from `patches/bachata-v3/*.patch` are applied in order.

## Why this experiment is needed
The G720 log of 2026-11-12 selects Mesa 26.3.1 (p0175), which retains a different
tiler-heap lifecycle than Bachata V3. The Bachata patch 0007 restores GPU-side
heap chunk recycling by default (`PANVK_KBASE_SKIP_HEAP_OPS=1` reverses it);
patch 0005 enables GPU waits for same-queue semaphores by default
(`PANVK_KBASE_GPU_SEMAPHORE_WAITS=0` reverses it). Neither patch makes
runtime gains or stability on G720 *certain*; Bachata V3 qualification is G615.

## Build and install, without a new APK
GitHub Actions:
https://github.com/erickmendes22/gow3_android_daedalus_fork/actions/workflows/gow3-bachata025-panvk-parity-bionic.yml
Once a run succeeds, its artifact
`GoW3-PanVK-Bachata-025-8patches-Bionic-ARM64-UNTESTED`
contains `PanVK-Bachata025-8patch-Bionic-EXPERIMENTAL.zip`. Extract that ZIP
from the GitHub Actions artifact container (do not feed the outer artifact ZIP
to the driver importer). In GoW III, use GPU Drivers > Import driver and choose
the **inner ZIP**. The launcher supports custom Bionic PanVK ZIPs with root
`meta.json` and `libvulkan_panfrost.so`. Importing selects the new driver.
To restore, select the previous PanVK 26.3.1 or automatic profile.

## Comparison gate
- Device: **same Poco X7 Pro, G720 MC7**, same temperature/cooler and charge,
  same GoW III save, no changed game patches.
- Both run at **1280x720**. Do *not* compare the 854x480 Bachata screen with a
  GoW III 720p screen and attribute all differences to the renderer.
- Warm shaders identically and play the same 45–60 seconds of the scene at
  ~2500 draws/frame; collect GoW FPS, frame time percentiles, `pm4_submit_wall`,
  `submit_vk_queue`, `gpu_tick` waits, image allocations, RAM and crashes.
- Repeat runs in alternating order to reduce cache/thermal bias. Test texture
  appearance, video playback, autosave and mode transitions, not just FPS.
- No driver is set as universal/default from a synthetic compilation result.

## Separate GC experiment (does NOT establish steady-state FPS)
The source branch also implements capped batching of dirty texture-cache GC
downloads. The 2026-11-12 log had 26 synchronous downloads totalling 642.37 ms;
reducing the number of GPU drains should reduce that stutter if images do not
overlap. `GOW3_MALI_GC_BATCH_DOWNLOAD=0` restores the original path. Native
compile and source safety tests precede any device FPS claim.
