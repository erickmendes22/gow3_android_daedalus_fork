# Shadow of the Colossus — Android port

This is the initial, **preboot** Android/Bionic adaptation of
https://github.com/AjncSystem/ShadowOfTheColossus-PC.
It lives on the isolated sotc-android-port branch of Daedalus Fork.

Upstream uses the BBPROBE5 format and runs the game's PS4 x86-64 instructions
directly on Windows. Android ARM64 requires the FEX guest_cpu boundary used in
our God of War III, Uncharted and inFAMOUS ports. This is **not** a functioning
Android APK yet.

Implemented:
- Safe, non-destructive guest eboot mapping below 2 GiB. SotC packs pointers
  into 31 bits, unlike GoW3's 40-bit pointer range.
- Android-safe Python preparation using the original upstream PS4 dump/image
  linker, SotC CPU patcher, signature-checked mode patches, 60 FPS (game's own
  timing) and 1280x720 option, for EU CUSA08809 and US CUSA08034.
- Host unit tests and ARM64 Bionic cross-compile validation workflow.

Requires before packaging:
- Port SotC-specific loader, GPU HLE, resource readbacks and shaders to
  Android, retaining upstream game fixes.
- Bridge BBPROBE5, PS4 modules, guest entry/initializer callbacks, SSE4a,
  red zone, heap and GPU faults through the ARM64 FEX interface.
- Unique Android app ID, controller mapping, game import, saves and driver
  staging; compile, sign and test on Adreno.

No game assets, decrypted Sony modules or firmware can be distributed.
Do not relabel a GoW3 APK as SotC. GPL-2.0-or-later applies.

Example: python3 ports/sotc/android/prepare_game.py --upstream ./upstream-sotc --game-dir /your/CUSA08809 --out /private/sotc-data --render 1280x720 --modes fps60game
