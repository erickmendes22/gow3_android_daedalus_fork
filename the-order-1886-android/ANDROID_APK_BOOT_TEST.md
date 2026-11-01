# The Order: 1886 — Android Bionic 0.1.1 installer test

Standalone `com.daedalus.order1886` app: dark landscape launcher with Home, Graphics, Drivers, Tools; game process SurfaceView behind in-game controls. The source code and the APK contain no commercial game data.

## Actual game installation and preparation

- **Install PKG / Install update**: local PS4 PKG opened with SAF, passed to the pinned Rust `orbis-pkg-util` extractor **without copying the entire PKG**; saved in `/storage/emulated/0/TheOrder1886/Games/<TITLE_ID>` (updates merge into the selected game with validated matching TITLE_ID). Requires All Files Access and a local file, not a cloud document. The six The Order editions declared by PC upstream are recognized. The installer does not decrypt unsupported packages or supply console keys.
- **Select existing game**: select an extracted local folder via Android folder picker, checked for `eboot.bin` and `sce_sys/param.sfo`.
- **Prepare game**: the Bionic CPython 3.13 binary from our donor runtime executes the *pinned PC-port* `order1886.py --prepare-only` and source scripts on Android, generating `user/prepared/boot-linked.bin` in app-private storage, without editing the original game dump. Requires the decoded game's `sce_module/libc.prx` and `libSceFios2.prx` too. The prep toolchain is an APK asset extracted on first preparation.
- **Import prepared image** stays as an advanced fallback; not required in the intended normal flow.
- **Drivers**: system Vulkan by default, import standard AdrenoTools Turnip ZIPs containing a valid `meta.json` and ARM64 Vulkan library; chosen custom driver is passed as `ORDER1886_VULKAN_DRIVER` to the *Order-specific* direct ICD/HAL loader.
- **Graphics**: 30/60 FPS, 1920/1600/1280 render width, original/16:9 are prepared by PC-port scripts. Readback mode, VSync, fullscreen, touch overlay and background warmup flow into Android runtime. No unsupported pretend settings.

The same APK keeps native ARM64 GPU `libps4gpu.so`, CPU `liborder1886cpu.so`, receiver `liborder1886present.so`, executable probe, cargo-built PKG extractor, Python interpreter/lib and a ZIP of Python stdlib plus *source-only* preparation scripts.

**Not a gameplay verification:** Passing CI validates source, native links and APK packaging. Testing the APK on real hardware is still required for CPU JIT, GPU rendering, imported Turnip compatibility, Python preparation and PKG extraction. Logs are exportable. No God of War III release branches have been changed.
