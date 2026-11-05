#!/system/bin/sh
# Run from the app's private executable directory. No Debian loader, rootfs, X11 or Python.
set -eu
base=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
choice=${GOW3_BIONIC_DRIVER:-auto}
case "$choice" in
    auto)
        chip=$("$base/bin/kgsl-chip-id" 2>/dev/null || true)
        case "$chip" in
            0x44??????) export GOW3_VULKAN_DRIVER="$base/drivers/gen8/libvulkan_freedreno.so" ;;
            *) unset GOW3_VULKAN_DRIVER
               echo "No confirmed Adreno Gen8 chip ID ($chip); testing system Vulkan" ;;
        esac ;;
    system) unset GOW3_VULKAN_DRIVER ;;
    gen8) export GOW3_VULKAN_DRIVER="$base/drivers/gen8/libvulkan_freedreno.so" ;;
    *) echo "GOW3_BIONIC_DRIVER must be auto, system or gen8" >&2; exit 2 ;;
esac
# Avoid silently claiming that the requested custom driver worked after a fallback.
if [ -n "${GOW3_VULKAN_DRIVER:-}" ] && [ ! -f "$GOW3_VULKAN_DRIVER" ]; then
    echo "Selected driver is missing: $GOW3_VULKAN_DRIVER" >&2; exit 1
fi
exec "$base/bin/gow3-vulkan-check"
