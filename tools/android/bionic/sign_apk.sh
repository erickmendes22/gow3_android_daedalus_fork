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
mkdir -p "$(dirname "$key")" "$(dirname "$apk")"
# Preserve the signing identity already installed on user devices.
# A missing cache/key must fail, never create an unrelated replacement key.
if [[ ! -s $key ]]; then
    echo "The established Daedalus APK signing key is missing; refusing a non-upgradeable build" >&2
    exit 1
fi
"$bt/zipalign" -P 16 -f 4 "$unsigned" "$root/out/release/bionic-aligned.apk"
"$bt/apksigner" sign --ks "$key" --ks-key-alias bionic --ks-pass pass:android --key-pass pass:android \
    --out "$apk" "$root/out/release/bionic-aligned.apk"
"$bt/apksigner" verify --verbose "$apk"
python3 tools/android/bionic/validate_apk.py "$apk" --aapt "$bt/aapt"
(cd out/release; sha256sum "$(basename "$apk")" > "$(basename "$apk").sha256")
echo "Daedalus Fork Bionic APK: $apk"
