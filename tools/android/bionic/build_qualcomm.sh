#!/usr/bin/env bash
set -Eeuo pipefail
cd -- "$(dirname -- "$0")/../../.."
ndk=${GOW3_NDK:-${ANDROID_NDK_HOME:-}}
: "${ndk:?Set GOW3_NDK or ANDROID_NDK_HOME}"
api=${GOW3_BIONIC_API:-30}
revision=8fae8ce254dfc1344527e05301e43f37dea2df80
checkout="$PWD/.local-deps/android/libadrenotools"
build="$PWD/out/bionic/adrenotools-build"
stage="$PWD/out/bionic/qualcomm"
mkdir -p "$(dirname "$checkout")" "$stage"
if [[ ! -d "$checkout/.git" ]]; then
    git clone https://github.com/bylaws/libadrenotools.git "$checkout"
fi
git -C "$checkout" checkout --detach --force "$revision"
git -C "$checkout" submodule update --init --recursive
python3 - "$checkout/src/hook/hook_impl.cpp" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()
fallback = 'LOGI("hook_android_dlopen_ext: falling back!");'
loaded = 'return handle;\n    } else {'
if text.count(fallback) != 1 or text.count(loaded) != 1:
    raise SystemExit('libadrenotools hook differs from the pinned source')
text = text.replace(fallback, fallback + '''
        if (hook_params->featureFlags & ADRENOTOOLS_DRIVER_CUSTOM) {
            std::fprintf(stderr, "GoW III Qualcomm: vendor hook failed; refusing system fallback\\n");
            return static_cast<void*>(nullptr);
        }''')
text = text.replace(loaded, '''std::fprintf(stderr, "GoW III Qualcomm: custom ICD loaded: %s%s\\n",
                     hook_params->customDriverDir.c_str(), hook_params->customDriverName.c_str());
        ''' + loaded)
path.write_text(text)
PY
cmake -S "$checkout" -B "$build" -G Ninja \
    -DCMAKE_TOOLCHAIN_FILE="$ndk/build/cmake/android.toolchain.cmake" \
    -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM="android-$api" \
    -DANDROID_STL=c++_shared -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON
cmake --build "$build" --parallel "${GOW3_JOBS:-2}"
for library in libadrenotools.so libhook_impl.so libmain_hook.so libfile_redirect_hook.so libgsl_alloc_hook.so; do
    built=$(find "$build" -name "$library" -type f -print -quit)
    [[ -n "$built" ]] || { echo "Missing $library from Android build" >&2; exit 2; }
    cp "$built" "$stage/$library"
done
cp "$checkout/LICENSE" "$stage/libadrenotools-LICENSE.txt"
"$ndk/toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android${api}-clang" \
    -std=c11 -O2 -Wall -Wextra -Werror -fPIC -fvisibility=hidden -shared \
    -Ithird_party/FEX/External/Vulkan-Headers/include \
    tools/android/bionic/qualcomm_vulkan.c -ldl -Wl,-z,defs \
    -Wl,-soname,libgow3qualcommvulkan.so -Wl,-z,max-page-size=16384 \
    -o "$stage/libgow3qualcommvulkan.so"
