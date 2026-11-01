# The Order: 1886 — Android Bionic staging

**Development status: CPU/FEX boundary port in progress; no working APK or Android gameplay claim.**

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

## Not done / blocks to first APK

1. Native ARM64 syntax, link and FEX runtime tests; build settings for `order1886cpu`.
2. Compile The Order renderer with the Android toolchain and remove desktop SDL/X11 assumptions without losing the Order renderer fixes.
3. Integrate Android Vulkan ICD/Turnip, AHardwareBuffer presentation and Android window/input/audio bridges.
4. Port Order's Python preparation, launcher, PKG install, saves/logs and test on a real device.
5. Repair any x86-only runtime paths revealed by actual builds and instrumented boots.

A passing static smoke check does **not** mean the game boots, renders, or performs well.
No existing GoW III Android release branch was modified. GPL obligations and third-party
copyright attribution remain applicable; this work is not affiliated with the rights holder.
