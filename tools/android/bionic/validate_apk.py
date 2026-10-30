#!/usr/bin/env python3
"""Validate the separate, game-free Bionic APK rather than the glibc release layout."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import zipfile


def validate_payload(payload, expected_hash):
    if hashlib.sha256(payload).hexdigest() != expected_hash.strip():
        raise ValueError('Runtime payload hash mismatch')
    with tarfile.open(fileobj=io.BytesIO(payload), mode='r:gz') as archive:
        members = {m.name: m for m in archive.getmembers()}
        for name, member in members.items():
            if name.startswith('/') or '..' in Path(name).parts or member.issym() or member.islnk():
                raise ValueError(f'Unsafe runtime member: {name}')
            if name.startswith('rootfs/') or Path(name).name.lower() in {
                    'eboot.bin','eboot.elf','boot-linked.bin','content.bin','patches.bin','lossless.dll'}:
                raise ValueError(f'Unexpected game/glibc content: {name}')
            # The old Vulkan-layer LSFG remains prohibited. The pinned MIT
            # Bloodframe engine is in-process, not a layer; its third-party
            # license may legitimately contain "lsfg-vk" in the filename.
            # Allow that ONLY as a regular license file in the notices dir.
            parts = Path(name).parts
            third_party_license = (
                len(parts) == 3 and parts[:2] == ('gow3port', 'licenses') and
                parts[2].lower().startswith('bloodframe-') and
                'license' in parts[2].lower() and
                parts[2].lower().endswith(('.md', '.txt', '.license')) and
                member.isfile()
            )
            if any('lsfg' in part.lower() for part in parts) and not third_party_license:
                raise ValueError(f'Removed frame-generation component in runtime: {name}')
            if name.endswith('.pkg'):
                raise ValueError('Player PKG must never be packaged')
        required = ['runtime-manifest.json','gow3port/run-bionic.sh',
                    'gow3port/arm64/bin/gow3-probe','gow3port/arm64/bin/gow3-prepare',
                    'gow3port/arm64/bin/orbis-pkg-util','gow3port/arm64/bin/kgsl-chip-id',
                    'gow3port/arm64/lib/libgow3cpu.so','gow3port/arm64/lib/libgow3gpu.so',
                    'gow3port/arm64/lib/libgow3present.so',
                    'gow3port/arm64/lib/libbloodframe.so',
                    'gow3port/arm64/lib/libc++_shared.so',
                    'gow3port/arm64/python/bin/python3.13',
                    'gow3port/arm64/python/lib/libpython3.13.so',
                    'gow3port/scripts/patches.py','gow3port/scripts/game_update.py',
                    'gow3port/scripts/launch_env.py','gow3port/gow3.default.ini']
        for name in required:
            if name not in members or not members[name].isfile():
                raise ValueError(f'Missing Bionic runtime file: {name}')
        for name in required:
            if '/bin/' in name or name.endswith('/run-bionic.sh'):
                if not members[name].mode & 0o111:
                    raise ValueError(f'Runtime executable bit missing: {name}')
        bloodframe = archive.extractfile('gow3port/arm64/lib/libbloodframe.so').read(4)
        if bloodframe != b'\x7fELF':
            raise ValueError('Bloodframe native engine missing ELF signature')
        if not any(
            name.startswith('gow3port/licenses/bloodframe-') and
            'license' in name.lower() and entry.isfile()
            for name, entry in members.items()
        ):
            raise ValueError('Bloodframe upstream license notices are missing')
        identity = json.load(archive.extractfile('runtime-manifest.json'))
        if (identity.get('schema'),identity.get('runtime_backend'),identity.get('application_id')) != (
                1,'bionic','com.gow3.android.bionic'):
            raise ValueError('Wrong Bionic runtime identity')
        for key, directory in [('driver', 'gen8'), ('adreno7xx_driver', 'adreno7xx')]:
            spec = identity[key]
            driver = archive.extractfile('gow3port/arm64/drivers/'+directory+'/'+spec['library']).read()
            if hashlib.sha256(driver).hexdigest() != spec['library_sha256']:
                raise ValueError('Bundled driver differs from the exact pinned build: '+directory)



def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('apk',type=Path)
    p.add_argument('--aapt',required=True)
    a=p.parse_args()
    badging=subprocess.check_output([a.aapt,'dump','badging',str(a.apk)],text=True)
    for expected in ["name='com.gow3.android.bionic'","sdkVersion:'30'","targetSdkVersion:'28'",
                     "native-code: 'arm64-v8a'","versionName='2.1.8-bionic'"]:
        if expected not in badging:raise ValueError('APK identity mismatch: '+expected)
    with zipfile.ZipFile(a.apk) as apk:
        apk.getinfo('lib/arm64-v8a/libgow3present.so')
        validate_payload(apk.read('assets/runtime.payload'),apk.read('assets/runtime.sha256').decode())
    print('Validated separate ARM64 Bionic APK: identity, payload hash, driver pin and game-free contents')

if __name__=='__main__':main()
