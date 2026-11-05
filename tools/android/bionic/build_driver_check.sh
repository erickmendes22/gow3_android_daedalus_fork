#!/usr/bin/env bash
# First migration milestone: Android/Bionic Vulkan validation, not a playable game runtime.
set -euo pipefail
cd -- "$(dirname -- "$0")/../../.."
ndk=${GOW3_NDK:-${ANDROID_NDK_HOME:-}}
: "${ndk:?Set GOW3_NDK or ANDROID_NDK_HOME to an installed Android NDK}"
api=${GOW3_BIONIC_API:-30}
out=$PWD/out/bionic-driver-check
unset CFLAGS CXXFLAGS CPPFLAGS LDFLAGS CPATH C_INCLUDE_PATH CPLUS_INCLUDE_PATH LIBRARY_PATH CMAKE_PREFIX_PATH
cmake -S tools/android/bionic -B "$out/build" -G Ninja \
    -DCMAKE_TOOLCHAIN_FILE="$ndk/build/cmake/android.toolchain.cmake" \
    -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM="android-$api" -DANDROID_STL=c++_static \
    -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$out"
cmake --build "$out/build" --parallel "${GOW3_JOBS:-2}"
cmake --install "$out/build"
cp tools/android/bionic/check-driver.sh "$out/"
chmod +x "$out/check-driver.sh"
# Optional local archive; otherwise fetch the published file whose SHA matches the attachment.
args=()
if [[ -n ${GOW3_BIONIC_DRIVER_ZIP:-} ]]; then args=(--archive "$GOW3_BIONIC_DRIVER_ZIP"); fi
python3 tools/android/bionic/stage_driver.py "${args[@]}" --output "$out/drivers/gen8"
echo "Android driver check: $out (not an APK/game runtime)"
