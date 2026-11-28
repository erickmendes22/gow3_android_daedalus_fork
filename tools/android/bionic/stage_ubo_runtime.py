#!/usr/bin/env python3
"""Stage a Snapdragon UBO test runtime using the verified GoW III 2.1.8 assets."""
import argparse
import hashlib
import io
from pathlib import Path
import subprocess
import tarfile
import tempfile
import zipfile

BASELINE_APK_SHA256 = 'bffc0edf6e70738423963ede8a76a2a0274320f6e18671302a0a589a6dcc879f'
GPU = 'gow3port/arm64/lib/libgow3gpu.so'
PROBE = 'gow3port/arm64/bin/gow3-probe'
NATIVE_LIBRARIES = ('libgow3cpu.so', 'libgow3present.so', 'libbloodframe.so', 'libc++_shared.so')


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def symbols(llvm_nm, elf, *mode):
    table = subprocess.check_output([llvm_nm, '-D', '--format=posix', *mode, elf], text=True)
    return {line.split()[0] for line in table.splitlines() if line.strip()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline', type=Path)
    parser.add_argument('gpu', type=Path)
    parser.add_argument('llvm_bin', type=Path)
    args = parser.parse_args()
    apk_data = args.baseline.read_bytes()
    if sha256(apk_data) != BASELINE_APK_SHA256:
        raise ValueError('Baseline APK failed SHA-256 verification')

    root = Path(__file__).resolve().parents[3]
    assets = root / 'out/android-release/assets'
    apk_jni = root / 'out/bionic/apk-jni/arm64-v8a'
    assets.mkdir(parents=True, exist_ok=True)
    apk_jni.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(apk_data)) as apk, tempfile.TemporaryDirectory() as work:
        payload = apk.read('assets/runtime.payload')
        if sha256(payload) != apk.read('assets/runtime.sha256').decode().strip():
            raise ValueError('Baseline payload hash does not match its manifest')
        for name in ('libfxio.so', 'libfxdisplay.so'):
            if (root / 'tools/android/bridges/arm64-v8a' / name).read_bytes() != apk.read(
                'lib/arm64-v8a/' + name
            ):
                raise ValueError(f'JNI bridge differs from baseline: {name}')
        (apk_jni / 'libgow3present.so').write_bytes(apk.read('lib/arm64-v8a/libgow3present.so'))
        driver = 'drivers/PanVK-android-v3.2-universal-2a9358a.zip'
        (assets / driver).parent.mkdir(exist_ok=True)
        (assets / driver).write_bytes(apk.read('assets/' + driver))

        with tarfile.open(fileobj=io.BytesIO(payload), mode='r:gz') as source:
            work = Path(work)
            old_gpu = work / 'libgow3gpu-original.so'
            old_gpu.write_bytes(source.extractfile(GPU).read())
            new_gpu = work / 'libgow3gpu.so'
            new_gpu.write_bytes(args.gpu.read_bytes())
            subprocess.run([args.llvm_bin / 'llvm-strip', '--strip-unneeded', new_gpu], check=True)
            nm = args.llvm_bin / 'llvm-nm'
            original_exports = symbols(nm, old_gpu, '--defined-only')
            imports = set()
            for name in (PROBE, *('gow3port/arm64/lib/' + name for name in NATIVE_LIBRARIES)):
                consumer = work / Path(name).name
                consumer.write_bytes(source.extractfile(name).read())
                imports |= symbols(nm, consumer, '--undefined-only')
            missing = (imports & original_exports) - symbols(nm, new_gpu, '--defined-only')
            if missing:
                raise ValueError(f'Native runtime references missing GPU symbols: {sorted(missing)}')

            replacements = {
                GPU: new_gpu.read_bytes(),
                'gow3port/run-bionic.sh': (root / 'tools/android/bionic/run-bionic.sh').read_bytes(),
                'gow3port/scripts/launch_env.py': (root / 'scripts/launch_env.py').read_bytes(),
                'gow3port/scripts/patches.py': (root / 'scripts/patches.py').read_bytes(),
            }
            with tarfile.open(assets / 'runtime.payload', 'w:gz', compresslevel=6) as target:
                for member in source:
                    if member.name in replacements:
                        data = replacements.pop(member.name)
                        member.size = len(data)
                        target.addfile(member, io.BytesIO(data))
                    else:
                        target.addfile(member, source.extractfile(member) if member.isfile() else None)
            if replacements:
                raise ValueError(f'Baseline payload is missing entries: {sorted(replacements)}')
        digest = sha256((assets / 'runtime.payload').read_bytes())
        (assets / 'runtime.sha256').write_text(digest + '\n')
        print(f'Validated baseline dependencies and staged the new ARM64 GPU runtime: {digest}')


if __name__ == '__main__':
    main()
