#!/usr/bin/env bash
set -Eeuo pipefail
cd -- "$(dirname -- "$0")/../../.."
root=$PWD
sdk=${ANDROID_HOME:-${ANDROID_SDK_ROOT:-}}
: "${sdk:?Set ANDROID_HOME or ANDROID_SDK_ROOT}"
bt="$sdk/build-tools/${GOW3_BUILD_TOOLS:-35.0.0}"
unsigned="$root/android-launcher/app/build/outputs/apk/release/app-arm64-v8a-release-unsigned.apk"
apk="$root/out/release/God-of-War-III-Daedalus-Fork-v2.1.8-bionic-arm64.apk"
key="$root/.local-deps/android/bionic-development.keystore"
validate_args=()
sign_args=(--ks-key-alias bionic --ks-pass pass:android --key-pass pass:android)
if [[ ${GOW3_MALI_TEST_APK:-0} == 1 ]]; then
    # A separately installable diagnostics app, NOT an upgrade/replacement.
    # Reuse the repository's existing development key for repeatable testing.
    key="$root/tools/android/debug/gow3-debug.keystore"
    apk="$root/out/release/God-of-War-III-Mali-Diagnostic-v2.1.8-arm64.apk"
    validate_args+=(--mali-test)
    sign_args=(--ks-pass pass:android --key-pass pass:android)
fi
mkdir -p "$(dirname "$key")" "$(dirname "$apk")"
if [[ ! -s $key ]]; then
    echo "The required signing identity is missing: $key" >&2
    exit 1
fi
if [[ ${GOW3_MALI_TEST_APK:-0} == 1 ]]; then
    keytool -list -keystore "$key" -storepass android >/dev/null 2>&1 ||
        { echo "Development signing key cannot be unlocked" >&2; exit 1; }
fi
"$bt/zipalign" -P 16 -f 4 "$unsigned" "$root/out/release/bionic-aligned.apk"
"$bt/apksigner" sign --ks "$key" "${sign_args[@]}" \
    --out "$apk" "$root/out/release/bionic-aligned.apk"
"$bt/apksigner" verify --verbose "$apk"
python3 tools/android/bionic/validate_apk.py "$apk" --aapt "$bt/aapt" "${validate_args[@]}"
(cd out/release; sha256sum "$(basename "$apk")" > "$(basename "$apk").sha256")
echo "Daedalus Fork Bionic APK: $apk"
