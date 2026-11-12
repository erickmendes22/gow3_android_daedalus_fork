# Bachata S4 0.2.5 vs GoW III Mali — binary-backed gap analysis (2026-11-12)

## Evidence / provenance
- Official release: https://github.com/JICA98/Bachata-S4/releases/tag/v0.2.5 ; APK `bachatas4-0.2.5-release.apk`, 211009680 bytes, SHA-256 `1df49463f396df8b6f042230bdc1bb9f948b8e69894c378915920875c40ab0ee`. Signature matches GitHub release asset metadata and binary audit runtime.
- Successful direct ELF audit, no APK generated: https://github.com/erickmendes22/gow3_android_daedalus_fork/actions/runs/43317754366 and follow-up https://github.com/erickmendes22/gow3_android_daedalus_fork/actions/runs/43318750414.
- GoW3 compared: artifact `GoW3-Mali-PM4-Coroutine-Native-Verified`, workflow https://github.com/erickmendes22/gow3_android_daedalus_fork/actions/runs/43303537921. Separate APK artifact from the same run includes bundled drivers.
- Device log used: `GodOfWar3-Logs-20261112-183427.zip` (Mali-G720 MC7).

## Actual binaries — not equivalently built
| Component | Bachata v0.2.5 | GoW III |
| --- | --- | --- |
| Native Android renderer | `libbachata_native_runtime.so`, 85583216 bytes, SHA `147fd32524cbf21c8946c6e93bd6e3d50ed325251aa4acae5a284f456ce6a9f4` | `libgow3gpu.so`, 198348984 bytes, SHA `ed071c696554fcafd003ad79482316f5555c86126c81afc45934c7e33f798cdd` |
| Linux host engine | `host/shadps4-arm64-fex`, 75323616 bytes, glibc ELF | GoW III Bionic in-process engine; not ABI-equivalent |
| PanVK official | `libvulkan_panfrost.so`, 22133360 bytes, SHA `fe60e41514698e5430551adc8718e315ab16325406b1da3af44e40e615ca4af4` (glibc) | Bundled V3.2 Bionic 21506944 bytes, SHA `9002ddaf65a16b3a4b404a5004ac6952a075879809415bd01aa0ec93d118b971`; bundled Mesa 26.3.1 Bionic 34850936 bytes, SHA `62c2b3f98ca987d5ab50b6f01e2d2c1c5b3ee995fe93666aa5da9415f65c3348` |
| Actual active PanVK in supplied log | No same-session Bachata log supplied here | Imported driver directory `0c61ef0cdd5c9314715c4a0cc34a5929dbd727ce7a30545b947577e83600b900` matches published ZIP SHA of `Mesa-PanVK-Android-v26.3.1-795ca7ff.adpkg.zip`; **not Bachata V3** |

## Structural differences detected by actual binary strings
1. Bachata native contains mangled symbols for `Vulkan::CommandRecorder::Reserve/Publish/Sync/WorkerLoop`. GoW has `Vulkan::Scheduler::RecorderThread`, `RecordChunk`, `DrawPipe`. This is a real **architectural difference**, but not itself proof of a throughput advantage. In GoW's heavy frame stats, recorder blocking is <1% of wall time, so do not blindly rewrite threading.
2. Bachata native contains `VideoCore::TileManager::EncodeEtc2` and `GetEtc2EncodePipeline`, plus `Vulkan::Instance::AddTransientEtc2Bytes/RemoveTransientEtc2Bytes`. GoW has `Vulkan::BcnTranscodeState::Record/RecordBatch` for BC1/BC3 uploads to ETC2. Need compare **which resource transitions** use each path, not assume they are functionally identical or that GoW lacks ETC2 transcode.
3. Bachata native contains `Vulkan::Instance::RefreshAllocatorMemoryBudget/GetLiveGpuMemoryBudget` and `GPU_MEMORY_TELEMETRY` strings. GoW uses `GetDeviceMemoryBudgetNow`, periodic GC and VMA pools. Investigate budget accounting and **incompatible allocation shapes** before copying GC thresholds.
4. Both Bachata V3 and GoW V3.2 PanVK ELF contain `PANVK_KBASE_THREADED_SUBMIT`, `PANVK_KBASE_GPU_SEMAPHORE_WAITS`, `PANVK_KBASE_SKIP_HEAP_OPS`, `PANVK_KBASE_HEAP_RENEW_WORK` and `PANVK_KBASE_HEAP_RENEW_INTERVAL` strings: their existence does not establish their default values.
5. Mesa 26.3.1 Bionic has extra `PANVK_PRELOAD_BARRIER_TRACK`, `PANVK_TESS_DRAWBARRIER`, `PANVK_V9_TILER_HEAP_MB` markers. Determine defaults and usage in that driver before altering flags. The current GoW launcher does not set these flags explicitly.

## Latest G720 game log (1280x720, CUSA01715 v1.02)
- Heavy scene: 5.7 FPS with 2536–2767 draws/frame; another interval 3.7 FPS with 3047 draws/frame.
- Frame-stats GPU-tick blocked fractions ~81.7% and ~81.2% at 5.7 FPS. **These are CPU waiting fractions, not direct GPU occupancy.**
- In a heavy 10.512 s diagnostic interval, total `submit_throttle` was just 4.85 ms across 1503 waits; changing in-flight limit 2 to 8 is therefore not a supported primary performance fix.
- New graphics pipeline compilations generally zero in these steady-state heavy intervals. Optimizing shader warmup does not explain persistent 5.7 FPS.
- `GOW3_RGBA128_IMAGE_POOL` reaches 734 misses including 700 incompatible shapes, 34 empty, with only 34 exact hits; adjusting quota alone cannot fix mismatching VkImageCreateInfo.
- Three GC reports include 20+80+120 evictions, no writes in those reports, and up to 598 GPU-dirty images retained. A separate 7.185 s interval records 26 synchronous texture downloads totaling 642.37 ms (24.71 ms each on average, 188.46 ms worst), explaining **stutter**, not all steady-state low FPS.
- AHB copy is typically ~0.3–0.5 ms; overhead of this presentation alone cannot explain 175–270 ms frame times.

## Avoid false comparisons
- Previous Bachata G720 result was ~854x480; GoW log uses 1280x720 (2.25x the pixels). Compare both at the same output resolution to isolate pipeline/driver differences; preserve GoW 720p performance target separately.
- Bachata 0.2.5 ELF glibc and GoW Bionic ELF are **not directly linkable**. Do not copy `.so` and call it an implementation port.
- The published `zenithblue-oss/shadps4-arm64` main snapshot is not guaranteed to match the complete official 0.2.5 release ELF. Presence of a mangled name does not prove its runtime frequency or function behavior.

## Port candidates and acceptance gates
1. **Driver isolation first, without a new APK:** A/B on the same device, scene, settings and resolution using bundled PanVK V3.2 vs imported Mesa 26.3.1. This distinguishes driver regressions from core issues.
2. **CommandRecorder parity:** compare actual Vulkan command emission, queue submission boundaries, recorder wait and draw synchronization; port only if the Bachata strategy avoids demonstrated per-draw overhead not already handled by GoW.
3. **ETC2/resource lifetime parity:** inspect color image conversion and encode paths, compare exact-format pools and host allocations, preserve all texture contents. Confirm missing work before porting.
4. **Budget/writeback parity:** evaluate whether unified-memory budget reporting or grouping synchronous GC readbacks can reduce the measured 642 ms; do not violate guest-memory visibility or pool GPU-tick lifetimes.
5. **GPU pass measurements:** identify CPU-vs-GPU idle and expensive graphics passes; do not attribute GPU-tick wait time to fragment shaders without timestamps or matching driver counters.
6. **No speculative APK:** native compile, visual integrity and same-scene measured improvement before promoting experimental changes to release.
