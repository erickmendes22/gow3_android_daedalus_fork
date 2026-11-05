#!/usr/bin/env bash
set -euo pipefail
script_dir=$(cd -- "$(dirname -- "$0")" && pwd)
cd -- "$script_dir/../../.."

bash tools/android/debug/stage_debug_runtime.sh

# Steam sign-in libraries (SteamDllDialog.java); fetched on demand like the debug payload.
[[ -f .local-deps/android/steam-libs/jars.txt ]] || bash tools/android/inputs/fetch_steam_libs.sh

bash tools/android/apk/build_kotlin_launcher.sh
version=$(sed -n 's/.*versionName *= *"\([^"]*\)".*/\1/p' android-launcher/app/build.gradle.kts)
mkdir -p out/debug
cp android-launcher/app/build/outputs/apk/debug/app-arm64-v8a-debug.apk \
    "out/debug/God of War III-debug-$version.apk"
apk="out/debug/God of War III-debug-$version.apk"
sdk=${GOW3_ANDROID_SDK:-${ANDROID_SDK_ROOT:-$HOME/Library/Android/sdk}}
bt="$sdk/build-tools/${GOW3_BUILD_TOOLS:-35.0.0}"
"$bt/apksigner" verify "$apk"
"$bt/aapt" dump badging "$apk" | grep -F com.gow3.android >/dev/null
python3 tools/android/apk/validate_release_apk.py "$apk" --aapt "$bt/aapt" \
    --allow-debuggable --manifest tools/android/debug/runtime-manifest.json
if command -v shasum >/dev/null; then
    (cd out/debug && shasum -a 256 "$(basename "$apk")" > "$(basename "$apk").sha256")
fi
echo "Debug APK: out/debug/God of War III-debug-$version.apk"
