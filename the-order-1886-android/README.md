# The Order: 1886 — Android Bionic staging

**Development status: FEX CPU library built in CI; Android Vulkan/AHardwareBuffer source integration staged, not yet fully linked or gameplay-verified. No usable APK.**

This directory is a self-contained CPU-source overlay based on
[JulioCacko/The-Order-1886_pc](https://github.com/JulioCacko/The-Order-1886_pc)
at `c53cd01d032995fe622033623ab64b4cf6b02233`, with the ARM64 FEX interface
adapted from `erickmendes22/gow3_android_daedalus_fork` at
`b3a7c3d5e916cf8f4622192c0faa9383ebd77c00`.

## What is implemented in the overlay

- Original Order PS4BOOT5 loader, HLE, title-specific graphics and patches remain the upstream source.
- Guest x86-64 entry, imported host calls, linked module initializers and finalizers go through `guest_cpu`.
- Guest thread entry and GS/TLS follow the Bionic FEX bridge.
- Guest thread handle/TLS/stack allocations use low mappings on Android.
- FEXCore ARM64 sources, caller trampoline and Android compatibility header are carried from the existing donor.
- Android fault reporting uses the guest CPU register interface.

## Reproduce the source snapshot

```sh
git clone https://github.com/JulioCacko/The-Order-1886_pc.git order-source
git -C order-source checkout c53cd01d032995fe622033623ab64b4cf6b02233
python3 the-order-1886-android/scripts/assemble.py --source order-source --output order-android
python3 the-order-1886-android/scripts/smoke.py order-android
```

Never run the assembler on a game dump or in the upstream checkout; it only works with source code.
No game files, PKG, BIOS, proprietary drivers or decrypted saves are included.

## GPU source integration — staged, not yet confirmed working

The overlay preserves Order's own Vulkan renderer, presentation effects and shader logic while
introducing a Bionic headless window, Turnip/system loader, AHardwareBuffer-backed swapchain,
external semaphore sync-fd support and the Android Unix socket protocol. The Order-specific
presenter was adapted to use queue-family ownership transfers instead of desktop WSI
`ePresentSrcKHR`. These changes are source-level and require a real Android GPU build.

CPU proof: [FEXCore Android CI success](https://github.com/erickmendes22/gow3_android_daedalus_fork/actions/runs/41298404574).

## Not done / blocks to first APK

1. CPU-to-renderer linkage, guest memory and native startup tests (only FEX CPU library compiled).
2. **Compile** The Order renderer with NDK and remove remaining SDL/X11/desktop-only code without discarding Order-specific rendering fixes.
3. Connect the staged Android Vulkan loader/AHardwareBuffer protocol to the actual Java game activity and verify frame-fence ownership on hardware.
4. Port Order's Python preparation, launcher, PKG install, saves/logs and test on a real device.
5. Repair any x86-only runtime paths revealed by actual builds and instrumented boots.

A passing static smoke check does **not** mean the game boots, renders, or performs well.
No existing GoW III Android release branch was modified. GPL obligations and third-party
copyright attribution remain applicable; this work is not affiliated with the rights holder.
