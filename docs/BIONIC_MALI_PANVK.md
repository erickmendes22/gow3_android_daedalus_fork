# Experimental Mali GPU support (pre-GSR Bionic branch)

This branch starts from `fix/bionic-savedata-rich-load-ui-20261017` (GoW III Daedalus 2.1.6 Bionic, with no Snapdragon GSR2 renderer). It does not merge any subsequent GSR2 work.

## Scope

- The automatic GPU option still chooses the existing packaged Turnip drivers on Adreno 7xx and 8xx.
- On a non-Qualcomm device with `/dev/mali0`, no KGSL node and Android API >=35 (Android 15), the launcher installs and selects PanVK v3.2 from the APK.
- On Android 14 or earlier, unknown GPUs, or PanVK installation failure in automatic mode, use the system Vulkan loader. Explicit PanVK selection does not silently fall back.
- Player-selected, verified adrenotools-style driver ZIPs are never overridden by Automatic. PanVK can also be selected manually on eligible Mali devices.
- `tools/android/bionic/fetch_panvk.sh` obtains the exact PanVK v3.2 universal CSF ZIP from `ducvd89/Bloodborne-Android`; the SHA-256 is checked before APK packaging.

## Important limitation

The Bloodborne Android upstream includes PanVK as a testing-only driver and explicitly says its game does **not** run on Mali yet. This work brings its driver packaging and device-selection infrastructure to GoW III; it does **not** establish correct GPU features, Vulkan presentation, game boot, performance, or visual compatibility on Mali. Device logs and a Mali GPU test are essential.

## Validation

1. Confirm `GOW3_BIONIC_DRIVER=custom` with `GOW3_GPU_AUTO_REASON=PanVK 3.2 (Mali experimental)` on Mali G610+ / Android 15+.
2. Confirm `Vulkan: direct driver ... via vk_icdGetInstanceProcAddr` or `HMI` in the game log and check the `gow3-probe --vulkan-only` result before gameplay.
3. Check that an Adreno device continues to load Turnip, not PanVK.
4. Use Driver -> System / Automatic to revert if the PanVK Vulkan probe fails.

PanVK driver and Mesa license: see the upstream PanVK driver ZIP and Bloodborne-Android documentation. Do not claim Mali game support solely from a successful build.
