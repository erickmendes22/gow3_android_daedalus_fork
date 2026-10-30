#!/usr/bin/env python3
"""Reuse the exact released 2.1.8 runtime for a frontend-only build."""
import hashlib
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
BASE = '2fc5e4fe515fcb4e4d552fd529624d8497da116b'
APK_SHA = 'be49d0efdf83d1ea43b83dc997768176fc50c791c641ed45779ad19df74b6322'
PAYLOAD_SHA = 'b077e99225cb9db9a458ba02a769b77c64317a57addbfe543cdc17ab8f95de3e'

def main():
    apk = Path(sys.argv[1])
    if hashlib.sha256(apk.read_bytes()).hexdigest() != APK_SHA:
        raise ValueError('The baseline APK is not the validated 2.1.8 build')
    # Fail closed if this commit changes any input to the native runtime.
    changed = subprocess.check_output([
        'git', 'diff', '--name-only', BASE, 'HEAD', '--',
        'gpu', 'cpu', 'src', 'third_party', 'tools/android/bionic',
        'tools/android/config', 'tools/android/bridges', 'scripts', 'patches',
        'CMakeLists.txt', 'Cargo.toml', 'Cargo.lock'], cwd=ROOT, text=True)
    if changed.strip():
        raise ValueError('Native runtime inputs changed; a full build is required: ' + changed)
    with zipfile.ZipFile(apk) as archive:
        if archive.testzip() is not None:
            raise ValueError('Corrupt baseline APK')
        payload = archive.read('assets/runtime.payload')
        if hashlib.sha256(payload).hexdigest() != PAYLOAD_SHA:
            raise ValueError('Unexpected native runtime')
        for name in ['runtime.payload', 'runtime.sha256',
                     'drivers/PanVK-android-v3.2-universal-2a9358a.zip']:
            target = ROOT / 'out/android-release/assets' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read('assets/' + name))
        for name in ['libfxio.so', 'libfxdisplay.so']:
            if (ROOT / 'tools/android/bridges/arm64-v8a' / name).read_bytes() != archive.read('lib/arm64-v8a/' + name):
                raise ValueError('Tracked bridge differs from baseline: ' + name)
        target = ROOT / 'out/bionic/apk-jni/arm64-v8a/libgow3present.so'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(archive.read('lib/arm64-v8a/libgow3present.so'))
    print('Staged verified 2.1.8 native runtime; rebuilding Android frontend only')

if __name__ == '__main__':
    main()
