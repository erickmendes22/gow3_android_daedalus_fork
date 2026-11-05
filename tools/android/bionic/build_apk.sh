#!/usr/bin/env bash
# Separate experimental app; never replaces the stable glibc APK/runtime.
set -Eeuo pipefail
cd -- "$(dirname -- "$0")/../../.."
root=$PWD
ndk=${GOW3_NDK:-${ANDROID_NDK_HOME:-}}
: "${ndk:?Set GOW3_NDK or ANDROID_NDK_HOME}"
if [[ ${1:-} != --package-only ]]; then
    bash tools/android/bionic/build_runtime.sh
    bash tools/android/bionic/build_python.sh
    bash tools/android/bionic/build_pkg.sh
fi
python3 tools/android/bionic/verify_bionic.py --ndk "$ndk" --api "${GOW3_BIONIC_API:-30}" --root out/bionic --complete
package_args=()
if [[ ${GOW3_MALI_ONLY_BUILD:-0} == 1 ]]; then package_args+=(--mali-only); fi
gradle_args=()
if [[ ${GOW3_MALI_TEST_APK:-0} == 1 ]]; then
    package_args+=(--mali-test)
    gradle_args+=(-Pgow3MaliTest=true)
fi
python3 tools/android/bionic/package_runtime.py --ndk "$ndk" "${package_args[@]}"
# Mali-only experimental option: include SHA-pinned PanVK, never auto-select on Adreno.
bash tools/android/bionic/fetch_panvk.sh
"$root/android-launcher/gradlew" -p "$root/android-launcher" :app:assembleRelease -Pgow3Bionic=true "${gradle_args[@]}" --no-daemon --max-workers=2
bash tools/android/bionic/sign_apk.sh
