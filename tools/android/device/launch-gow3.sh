#!/usr/bin/env bash
set -euo pipefail
serial=${1:?usage: launch-gow3.sh ADB_SERIAL [cpu|vulkan|renderer|window|gamepads|controller|game]}
mode=${2:-game}
case $mode in cpu|vulkan|renderer|window|gamepads|controller|game) ;; *) echo 'Unknown mode' >&2; exit 2 ;; esac
app=com.gow3.android
files=/data/user/0/$app/files
loader="$files/rootfs/usr/lib/aarch64-linux-gnu/ld-linux-aarch64.so.1"
if [[ $mode == game || $mode == window ]]; then
  if ! adb -s "$serial" shell run-as "$app" test -S "$files/rootfs/tmp/.X11-unix/X0"; then
    # Recreate the activity so its developer-screen action is applied. Do not
    # force-stop: that also kills other app-owned processes and file transfers.
    adb -s "$serial" shell am start -f 0x10008000 -n "$app/.MainActivity" --es action x
    sleep 2
    for ((attempt=0; attempt<30; attempt++)); do
        if adb -s "$serial" shell run-as "$app" test -S "$files/rootfs/tmp/.X11-unix/X0"; then
            break
        fi
        sleep 1
    done
    adb -s "$serial" shell run-as "$app" test -S "$files/rootfs/tmp/.X11-unix/X0"
  fi
fi
exec adb -s "$serial" shell run-as "$app" "$loader" "$files/rootfs/bin/sh" "$files/gow3port/run-gow3.sh" "$mode"
