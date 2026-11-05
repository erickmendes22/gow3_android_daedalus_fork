#!/usr/bin/env bash
# Deploy the Linux experiment into the installed, debuggable fexdroid app.
set -euo pipefail
cd -- "$(dirname -- "$0")/../../.."
serial=${1:?usage: deploy_gow3.sh ADB_SERIAL [bundle-directory]}
bundle=${2:-out/thor/bundle}
app=com.gow3.android
files=/data/data/$app/files
adb_cmd=(adb -s "$serial")
"${adb_cmd[@]}" shell run-as "$app" test -x "$files/rootfs/usr/bin/FEX"
"${adb_cmd[@]}" shell run-as "$app" mkdir -p "$files/gow3port"
tar -C "$bundle" -cf - . | "${adb_cmd[@]}" shell -T run-as "$app" tar -xf - -C "$files/gow3port"
# Use the runtime's matching x86 Vulkan thunk, not an emulated x86 driver. The
# Debian/FEX rootfs is the only Linux root; never recreate it under gow3port.
"${adb_cmd[@]}" shell run-as "$app" cp \
    "$files/rootfs/usr/share/fex-emu/GuestThunks/libvulkan-guest.so" \
    "$files/rootfs/usr/lib/libvulkan.so.1"
echo "Deployed Linux bundle to $serial. Game data is copied separately."
