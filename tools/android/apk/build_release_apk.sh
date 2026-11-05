#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/../../.."
root=$PWD
version=$(sed -n '/versionName *=/{s/.*versionName *= *"\([^"]*\)".*/\1/p;q;}' android-launcher/app/build.gradle.kts)
apk="out/release/God-of-War-III-$version-Daedalus-Fork.apk"
# Steam sign-in libraries (SteamDllDialog.java); fetched on demand like the fexdroid payload.
[[ -f .local-deps/android/steam-libs/jars.txt ]] || bash tools/android/inputs/fetch_steam_libs.sh
python3 tools/android/runtime/build_release_runtime.py

# Stage the release runtime payload where the Kotlin launcher's release source set reads it
# (android-launcher/app/build.gradle.kts: out/android-release/assets).
mkdir -p out/android-release/assets
cp out/release/runtime.tar.gz out/android-release/assets/runtime.payload
cp out/release/runtime.sha256 out/android-release/assets/runtime.sha256

"$root/android-launcher/gradlew" -p "$root/android-launcher" :app:assembleRelease
unsigned="$root/android-launcher/app/build/outputs/apk/release/app-arm64-v8a-release-unsigned.apk"
[[ -f $unsigned ]] || { echo "build_release_apk: release APK was not generated: $unsigned" >&2; exit 1; }

sdk=${GOW3_ANDROID_SDK:-${ANDROID_SDK_ROOT:-}}
if [[ -z $sdk ]]; then
    case $(uname -s) in
        Darwin) sdk="$HOME/Library/Android/sdk" ;;
        *) sdk=/home/zfitcode/Android/Sdk ;;
    esac
fi
bt="$sdk/build-tools/${GOW3_BUILD_TOOLS:-35.0.0}"

key=${GOW3_KEYSTORE:-$root/.local-deps/android/gow3.keystore}
if [[ -n ${GOW3_KEYSTORE_PASSWORD:-} || -n ${GOW3_KEY_ALIAS:-} || -n ${GOW3_KEY_PASSWORD:-} ]]; then
    [[ -n ${GOW3_KEYSTORE_PASSWORD:-} ]] || { echo 'GOW3_KEYSTORE_PASSWORD is required for release signing' >&2; exit 1; }
    [[ -n ${GOW3_KEY_ALIAS:-} ]] || { echo 'GOW3_KEY_ALIAS is required for release signing' >&2; exit 1; }
    [[ -n ${GOW3_KEY_PASSWORD:-} ]] || { echo 'GOW3_KEY_PASSWORD is required for release signing' >&2; exit 1; }
    [[ -f $key ]] || { echo "configured keystore does not exist: $key" >&2; exit 1; }
    key_alias=$GOW3_KEY_ALIAS
    ks_pass='env:GOW3_KEYSTORE_PASSWORD'
    key_pass='env:GOW3_KEY_PASSWORD'
else
    if [[ ! -f $key ]]; then
        mkdir -p "$(dirname "$key")"
        echo "build_release_apk: generating a local development key at $key" >&2
        keytool -genkeypair -keystore "$key" -storepass android -keypass android -alias gow3 \
            -dname 'CN=gow3-android local development' -keyalg RSA -keysize 2048 -validity 10000 \
            >/dev/null 2>&1 ||
            { echo "build_release_apk: keytool failed to create $key" >&2; exit 1; }
    fi
    key_alias=gow3
    ks_pass='pass:android'
    key_pass='pass:android'
fi
mkdir -p out/release
"$bt/apksigner" sign --ks "$key" --ks-key-alias "$key_alias" \
    --ks-pass "$ks_pass" --key-pass "$key_pass" \
    --out "$apk" "$unsigned"
"$bt/apksigner" verify --verbose "$apk"
"$bt/aapt" dump badging "$apk" | grep -F com.gow3.android >/dev/null
unzip -l "$apk" | grep -F lib/arm64-v8a/ >/dev/null
python3 tools/android/validate_release_apk.py "$apk" --aapt "$bt/aapt"
(cd out/release && if command -v sha256sum >/dev/null; then
    sha256sum "$(basename "$apk")" > "$(basename "$apk").sha256"
else
    shasum -a 256 "$(basename "$apk")" > "$(basename "$apk").sha256"
fi)
echo "Release APK: $apk"
