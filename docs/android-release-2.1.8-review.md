# GoW III Daedalus Android 2.1.8 integration review

Base: `ff820f80` (the consolidated spatial GSR2 / PanVK / mobile branch).
Keep the installed Android package and release signing identity unchanged.

## Requested interface and drivers

- Use the latest approved 1280x576 XML/preview positions across the immersive
  window, independently of the 16:9 video rectangle. The existing Canvas input
  adapter remains, so gamepad bridging, editable positions and SaveDataDialog
  interception continue to work.
- Fixed visible left joystick; separate visible right-stick dodge panel; one
  Rage button sends L3 and R3 together. The compact weapon selector reveals
  D-pad input. Action IDs remain below icons for combos and QTEs.
- The nine action assets are pixel crops from the user's approved generated
  `Interface móvel de God of War III.png`. No replacement generic glyphs.
- Both display modes hide Android system bars. Fullscreen OFF fits centered
  16:9; ON stretches without cropping. Resizing releases held touch input.
- Red/blue correction is an optional Home switch, disabled by default. The
  native presenter applies image-view channel mapping, including the scaled
  display path. It does not alter guest textures or CPU readback bytes. The
  setting survives a native settings rewrite and takes effect on game start.
- Adreno 8xx: Gen8 V38 Patched. Adreno 6xx/7xx: v27.0.0-R1. Pinned ZIP and HAL
  hashes, AArch64 ABI and Bionic dependencies validated by `stage_driver.py`.
- PanVK eligibility uses Android 15+, a known Mali/Immortalis CSF renderer,
  actual Mali device node and no Qualcomm/Exynos classification. Exynos always
  launches system Vulkan, including when restored preferences select Turnip.
  Host eligibility tests do not claim physical-phone driver validation.
- English and pt-BR resource keys match. Native Android HUD/Bloodframe dialog
  strings and the fullscreen description now use the selected app language.

## Performance and stability comparison

Reviewed PC `R-V-L/gow3_pc` main `96debe8`, the available Uncharted Android
runtime, and inFAMOUS Android `54e08263`. Mechanisms are compared by code path,
not by option names. This is not a claim of measured phone FPS improvements.

| Mechanism | Finding in GoW3 | Decision |
| --- | --- | --- |
| PC exact-byte readback waits (`b776be7`) | Missing: image consumers waited for unrelated bytes on a shared tracking page | Integrated the exact-overlap queue path, only with stale readbacks and for image refresh/free consumers; CPU page protection remains unchanged |
| PC partial-height integer image views (`b646683`) | Already present behind `PartialHeightViews` | Preserve; no duplicate image-reuse path |
| PC saved SPIR-V / shader prefetch | `LoadPipelineStage` already loads stored SPIR-V; `StartBackgroundWarmUp` deduplicates stages and warms pipelines in background | Preserve the Android implementation instead of replacing it with the PC launcher/cache workflow |
| PC shared binary storage / migration | A different disk layout; current Android has driver-identified pipeline binary files and a driver cache | No incompatible cache migration in this release; not presented as a new FPS optimization |
| Uncharted fast UMA reads | Maps sparse arena memory after completed writes, with host visibility/coherency and side-queue policy | Do not copy into GoW3 texture readbacks; a different consumer/synchronization contract, not an equivalent drop-in flag |
| Uncharted 100-draw batches | Paired with the U2/U3 mapped-readback policy | Do not force an unmeasured 100-draw flush; retain GoW3 recording/copy batching and the existing bound of eight in-flight Android submissions |
| Uncharted idle-worker sleep | Installs executable-specific job-loop signatures/hooks | No offsets copied to GoW3. Its executable/job scheduling needs independent validation before this can be safe |
| inFAMOUS FEX cache policy | GoW3 already sets fixed DynamicL1Cache by default and preserves TSO | Preserve; no extra cache policy or weaker memory ordering |
| PC foreign-range reservation (`e7cb319`) | The actual fallback reserves around injected DLLs using Windows VirtualQuery/VirtualAlloc2 | Not applicable to Android/Bionic/FEX; do not import the Windows address-space policy |
| PC memory-allocation failure exit (`b6b35ac`) | Error reporting/termination, not a normal-play throughput mechanism | Do not market or introduce a new exit policy as a performance fix |
| inFAMOUS temporal motion / neighborhood recovery | Game-specific camera/depth and unconfirmed face fix; GSR2 is deliberately spatial in this GoW3 branch | Not integrated |

## Validation scope

Run the full existing Android and Bionic source suites, compile the changed Java
classes against the Android API library, and execute native readback-queue and
settings round-trip tests. The APK build must compile the full launcher and
native Android runtime, verify version/package/signature, and package all nine
control assets and both pinned Turnip drivers. Phone gameplay/FPS and PanVK on
supported physical Mali hardware remain device validation tasks.
