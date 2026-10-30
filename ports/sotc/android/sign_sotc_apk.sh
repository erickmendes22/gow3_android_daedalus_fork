#!/usr/bin/env bash
# Separate experimental SotC Android package, never overwrites GoW3 release.
set -Eeuo pipefail
cd -- "$(dirname -- "$0")/../../.."
sdk=${ANDROID_HOME:-${ANDROID_SDK_ROOT:-}}
: "${sdk:?Android SDK must be available}"
bt="$sdk/build-tools/${GOW3_BUILD_TOOLS:-35.0.0}"
unsigned=android-launcher/app/build/outputs/apk/release/app-arm64-v8a-release-unsigned.apk
apk=out/release/Shadow-of-the-Colossus-Daedalus-Android-0.1.4-boot-test-arm64.apk
key=.local-deps/android/sotc-development.keystore
test -s "$unsigned" || { echo "SotC unsigned APK missing" >&2; exit 1; }
mkdir -p "$(dirname "$key")" out/release
if [[ ! -f "$key" ]]; then
  keytool -genkeypair -keystore "$key" -storepass android -keypass android \
    -alias sotc-bionic -dname 'CN=SotC Android Daedalus experimental development' \
    -keyalg RSA -keysize 2048 -validity 10000
fi
"$bt/zipalign" -P 16 -f 4 "$unsigned" out/release/sotc-aligned.apk
"$bt/apksigner" sign --ks "$key" --ks-key-alias sotc-bionic \
    --ks-pass pass:android --key-pass pass:android --out "$apk" out/release/sotc-aligned.apk
"$bt/apksigner" verify --verbose "$apk"
"$bt/aapt" dump badging "$apk" > out/release/sotc-badging.txt
grep -Fq "package: name='com.sotc.android.daedalus'" out/release/sotc-badging.txt
grep -Fq "versionName='0.1.4-boot-test'" out/release/sotc-badging.txt
(cd out/release; sha256sum "$(basename "$apk")" > "$(basename "$apk").sha256")
echo "SotC Android Bionic boot-test APK: $apk"
