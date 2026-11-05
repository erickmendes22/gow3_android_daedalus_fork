# God of War III — Daedalus Fork · Bionic

**Version: 2.1.6-daedalus.4-bionic**

[Português (Brasil)](README.md) | **English**

Fork maintained by **erickmendes22 — [Daedalus Emulator](https://www.youtube.com/@daedalusemulator)**, based on [zFitness's Android project](https://github.com/zFitness/gow3_android) and the work of upstream contributors.

## Native Android/Bionic runtime

This version uses **Bionic, Android's native system library**, with **AHardwareBuffer** presentation and Vulkan integration for system or custom drivers.

The game's original **x86-64 code is still translated to ARM64 by FEXCore**, while the shadPS4-based renderer translates graphics to Vulkan.

The project is dedicated to **God of War III Remastered**.

## Main features

- **Driver selection:** system driver, bundled Turnip or a custom driver.
- **Selectable render resolutions**, including 720p, 900p and 1080p.
- **Performance and graphics synchronization improvements**, with shader, cache and data transfer optimizations.
- **Texture cache coherence fixes** in the renderer.
- **Optional patches** for graphics effects, shadows, videos and texture corruption.
- **Direct PKG installation**, including updates for the selected game.
- **Configurable FPS counter:** visibility, position and size.
- **English and Brazilian Portuguese interface**, including in-game settings.
- **Portuguese game language selection** based on the edition and languages available in the installed files.
- **Save management and log export.**

The current version uses **direct rendering, without FSR or LSFG**.

## Requirements

- **Android 11 or later.**
- **ARM64 — arm64-v8a** device; no root required.
- GPU and driver supporting the Vulkan features required by the runtime.
- Your own copy of **God of War III Remastered**.

Patches depend on the edition and executable version. The patches available in the catalog target update **01.02**.

## Installation

1. Download and install the APK from [Releases](https://github.com/erickmendes22/gow3_android_daedalus_fork/releases).
2. Grant the file access permission requested on first launch.
3. Select a folder containing the extracted game or use **Install PKG**.
4. Configure your preferred resolution, patches and driver.
5. Launch the game.

Performance varies with the device, driver, resolution and selected effects.

## Credits

- **erickmendes22 / Daedalus Emulator** — fork maintenance and Android adaptations.
- **[zFitness/gow3_android](https://github.com/zFitness/gow3_android)** — Android project used as the base.
- **[ducvd89/Bloodborne-Android](https://github.com/ducvd89/Bloodborne-Android)** — Android/Bionic infrastructure adapted for Vulkan driver loading, AHardwareBuffer presentation, native preparation and dependency builds.
- **[FelipePrado0/gow3_pc](https://github.com/FelipePrado0/gow3_pc)** and **[R-V-L/gow3_pc](https://github.com/R-V-L/gow3_pc)** — upstream projects and port improvements.
- **[deadinside28/bloodborne_pc](https://github.com/deadinside28/bloodborne_pc)** — project underlying the chain of ports.
- **[cuesta4/shadPS4](https://github.com/cuesta4/shadPS4)** and **[the shadPS4 team](https://github.com/shadps4-emu/shadPS4)** — renderer and graphics fixes.
- **[FEX-Emu](https://github.com/FEX-Emu/FEX)** — dynamic translation of x86-64 code to ARM64.
- **[fexdroid](https://github.com/cobrabm12/fexdroid)** — Android infrastructure used by the original project.
- **kvicken, cuesta4 and illusion0001** — patches and work underlying the resolution, texture, video and frame rate adaptations.
- **StevenMXZ, WinNative-Emu and Mesa/Turnip contributors** — bundled drivers and their fixes.

Further attribution is available in the [Bionic runtime notices](tools/android/bionic/NOTICE.txt) and the licenses of the included components.

## Support

**YouTube:** [@daedalusemulator](https://www.youtube.com/@daedalusemulator)  
**Issues and suggestions:** [GitHub Issues](https://github.com/erickmendes22/gow3_android_daedalus_fork/issues)

When reporting a problem, include your device, driver, game version and logs exported by the app.

## License

**GNU GPL v2 or later.** See [LICENSE](LICENSE). Third-party components retain their respective licenses.

No game files are distributed. This project is not affiliated with Sony Interactive Entertainment or Santa Monica Studio.
