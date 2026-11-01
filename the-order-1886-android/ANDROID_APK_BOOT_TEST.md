# The Order: 1886 — Bionic Android APK boot test

This is a separate Android Gradle module, `android-launcher/order1886`, with
application ID `com.daedalus.order1886`. It is not the God of War III app.
The Order-specific native library, FEX CPU bridge and AHardwareBuffer receiver
are compiled by `.github/workflows/order1886-bionic-gpu.yml` and packaged
into the dedicated APK. No proprietary game data is bundled.

The initial APK accepts a **PS4BOOT5 image already prepared on a PC** and a
path to a legally extracted game folder with `sce_sys/param.sfo`. It cannot
yet prepare an encrypted eboot.bin or install PKG files itself. The diagnostic
button invokes `order1886-probe --runtime-info`, without launching game data.
The native renderer uses the system Vulkan driver until a tested driver
selection UI is added. Physical controllers are passed through an atomic
Android pad-state file; on-screen controls are not yet implemented.

The first goal is validating native startup, dynamic links, imports, Vulkan
device selection, game initialization and the release/ownership of Android
hardware buffers. An installable APK by itself is *not* evidence of working
gameplay, sound or image presentation. Export the runtime log after a test.

Development status is kept distinct from upstream PC execution and from
the God of War III main release.
