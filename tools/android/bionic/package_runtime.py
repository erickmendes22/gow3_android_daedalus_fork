#!/usr/bin/env python3
"""Package only Android/Bionic runtime files; never include player game content."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[3]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ndk', type=Path, required=True)
    a = p.parse_args()
    source = ROOT/'out/bionic'
    strip = a.ndk/'toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-strip'
    output = ROOT/'out/release'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='gow3-bionic-stage-') as temp:
        stage = Path(temp)
        base = stage/'gow3port'
        runtime = base/'arm64'
        (stage/'home/gow3port/.fex-emu').mkdir(parents=True)
        (base/'user').mkdir(parents=True)
        (base/'logs').mkdir()
        for directory,names in {
            'bin':['gow3-probe','gow3-prepare','kgsl-chip-id','orbis-pkg-util'],
            'lib':['libgow3cpu.so','libgow3gpu.so','libgow3present.so','libbloodframe.so','libc++_shared.so']}.items():
            (runtime/directory).mkdir(parents=True)
            for name in names:shutil.copy2(source/directory/name,runtime/directory/name)
        shutil.copytree(source/'drivers',runtime/'drivers',ignore=shutil.ignore_patterns('.*'))
        # Reproducible Android Python install; keep stdlib modules, not build/test/development files.
        python = runtime/'python'
        (python/'bin').mkdir(parents=True)
        shutil.copy2(source/'python/bin/python3.13',python/'bin/python3.13')
        shutil.copytree(source/'python/lib',python/'lib',
                        ignore=shutil.ignore_patterns('__pycache__','test','tests','idlelib','tkinter',
                                                     'ensurepip','config-3.13*','site-packages'))
        shutil.copy2(source/'python/LICENSE-Python.txt',python/'LICENSE-Python.txt')
        shutil.copytree(ROOT/'scripts',base/'scripts',ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copytree(ROOT/'patches',base/'patches')
        shutil.copy2(ROOT/'tools/android/config/gow3-default.ini',base/'gow3.default.ini')
        shutil.copy2(base/'gow3.default.ini',base/'gow3.ini')
        shutil.copy2(ROOT/'tools/android/bionic/run-bionic.sh',base/'run-bionic.sh')
        fex = ROOT/'tools/android/config/gow3-fex-compatible.json'
        if fex.is_file():shutil.copy2(fex,stage/'home/gow3port/.fex-emu/bb-probe.json')
        notices = base/'licenses'
        notices.mkdir()
        shutil.copy2(ROOT/'LICENSE',notices/'LICENSE-Gow3.txt')
        shutil.copy2(ROOT/'android-launcher/app/src/main/assets/THIRD_PARTY_LICENSES.txt',notices/'THIRD_PARTY_LICENSES.txt')
        shutil.copy2(ROOT/'tools/android/bionic/NOTICE.txt',notices/'BIONIC-NOTICE.txt')
        shutil.copytree(ROOT/'tools/android/bionic/licenses',notices/'driver')
        for dep, license in [('fmt-12.1.0','LICENSE'),('zydis-4.1.1','LICENSE'),
                             ('zycore-1.5.2','LICENSE'),('xxhash-0.8.3','LICENSE'),
                             ('miniz-3.1.2','LICENSE'),('ffmpeg-7.1.5','COPYING.LGPLv2.1')]:
            shutil.copy2(ROOT/'.local-deps/android/bionic-src'/dep/license,notices/(dep+'-LICENSE.txt'))
        shutil.copy2(ROOT/'third_party/FEX/LICENSE',notices/'FEX-LICENSE.txt')
        shutil.copy2(source/'python/LICENSE-Python.txt',notices/'LICENSE-Python.txt')
        for name in ['LICENSE-MIT','LICENSE-APACHE']:
            shutil.copy2(ROOT/'.local-deps/android/orbis-pkg'/name,notices/('orbis-'+name))
        for f in list(runtime.rglob('*')):
            if 'drivers' not in f.relative_to(runtime).parts and f.is_file() and not f.is_symlink() and not f.name.startswith(".") and f.read_bytes()[:4]==b'\x7fELF':
                subprocess.run([str(strip),'--strip-unneeded',str(f)],check=True)
        jni = source/'apk-jni/arm64-v8a'
        jni.mkdir(parents=True,exist_ok=True)
        shutil.copy2(runtime/'lib/libgow3present.so',jni/'libgow3present.so')
        manifest={'schema':1,'runtime_backend':'bionic','application_id':'com.gow3.android.bionic',
                  'java_package':'ro.cobrabm.fexdroid','runtime_name':'daedalus-gow3-bionic-2.1.6-r4',
                  'version':'2.1.6-daedalus.4-bionic','min_api':30,
                  'driver':json.loads((ROOT/'tools/android/bionic/driver.json').read_text()),
                  'adreno7xx_driver':json.loads((ROOT/'tools/android/bionic/driver-adreno7xx.json').read_text())}
        (stage/'runtime-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        archive=output/'runtime.tar.gz'
        with tarfile.open(archive,'w:gz',compresslevel=6) as tar:
            for path in sorted(stage.iterdir()):tar.add(path,arcname=path.name)
        sha=hashlib.sha256(archive.read_bytes()).hexdigest()
        (output/'runtime.sha256').write_text(sha+'\n')
        assets=ROOT/'out/android-release/assets'
        assets.mkdir(parents=True,exist_ok=True)
        shutil.copy2(archive,assets/'runtime.payload')
        shutil.copy2(output/'runtime.sha256',assets/'runtime.sha256')
        print(f'Bionic runtime: {archive}, SHA256 {sha}')


if __name__=='__main__':main()
