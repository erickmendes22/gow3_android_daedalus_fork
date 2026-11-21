#!/usr/bin/env bash
# SotC 0.1.53 CI: produce only a page-aligned UNSIGNED APK.
# Do not generate ephemeral development keys in GitHub Actions. The original
# 0.1.49 signing identity remains private and is used for final local signing.
set -Eeuo pipefail
cd -- "$(dirname -- "$0")/../../.."
sdk=${ANDROID_HOME:-${ANDROID_SDK_ROOT:-}}
: "${sdk:?Android SDK must be available}"
bt="$sdk/build-tools/${GOW3_BUILD_TOOLS:-35.0.0}"
unsigned=android-launcher/app/build/outputs/apk/release/app-arm64-v8a-release-unsigned.apk
apk=out/release/Shadow-of-the-Colossus-Daedalus-Android-0.1.53-forest-performance-arm64-unsigned.apk
test -s "$unsigned" || { echo "SotC unsigned APK missing" >&2; exit 1; }
mkdir -p out/release
"$bt/zipalign" -P 16 -f 4 "$unsigned" "$apk"
"$bt/aapt" dump badging "$apk" > out/release/sotc-badging.txt
grep -Fq "package: name='com.sotc.android.daedalus'" out/release/sotc-badging.txt
grep -Fq "versionName='0.1.53-forest-performance'" out/release/sotc-badging.txt
(cd out/release; sha256sum "$(basename "$apk")" > "$(basename "$apk").sha256")
echo "SotC 0.1.53 CI unsigned APK, page-aligned and verified; fixed private key applied offline."
