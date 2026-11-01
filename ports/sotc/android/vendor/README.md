# GameHub DD 26.3 experimental Turnip — SotC Android

The emulator accepts the **exact ZIP supplied by the user**, with no renaming of the
driver library, stripping or binary modification.

- Expected ZIP SHA-256: `8255659cc205110e0fa89f2d364292b86fe563a2cedafbc41915bead5a611ecb`
- Expected `libvulkan_freedreno.so` SHA-256: `4f242a453496ab27fc29be950d632edbae494dcc0c9b7d56c37c7ebdffe42df9`
- Android 14+ / ARM64 Adreno only; experimental `PWR_MAX` patch can increase thermals.

**Bundled in APK:** put the original, unchanged ZIP at
`ports/sotc/android/vendor/turnip_gamehub_dd.zip` before running the GitHub
Action. The hash-gated packager includes the ELF at
`sotcport/arm64/drivers/gamehub-dd/libvulkan_freedreno.so` and records
`gamehub_dd_turnip_bundled=true` in `runtime-manifest.json`. An absent ZIP
does **not** mean the driver was bundled: the Action issues a warning.

**In-app import without the ZIP committed:** open the SotC launcher, select
**Import driver** and choose the same original GameHub DD ZIP. The importer
validates ARM64/Android compatibility; this exact archive gets the named
`gamehub-dd` driver entry, and the launcher selects it automatically. It
loads the original ELF from the app-private `gpu-drivers` directory via the
already supported Bionic `custom` HAL path. Other Turnip ZIPs remain ordinary
user-selected custom drivers.

This ZIP is user-provided, experimental, binary-patched software. Refrain from
changing the GPU memory/readback coherency workarounds purely to gain FPS.
The three SotC Vulkan CPU fastpaths operate independently of the selected
driver and can each be disabled in the UI.
