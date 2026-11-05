#!/usr/bin/env python3
"""Validate the signed, game-free Android release APK."""
import argparse
import hashlib
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

try:
    from .validate_runtime_archive import ArchiveError, validate_archive
except ImportError:
    from tools.android.runtime.validate_runtime_archive import ArchiveError, validate_archive


class ApkError(ValueError):
    pass


def _badging(apk, aapt):
    if not aapt:
        return ''
    result = subprocess.run([aapt, 'dump', 'badging', str(apk)],
                            check=False, capture_output=True, text=True)
    if result.returncode:
        raise ApkError('metadata: aapt dump badging failed: %s' % result.stderr.strip())
    return result.stdout


def validate_apk(apk, aapt=None, allow_debuggable=False, manifest=None):
    apk = Path(apk)
    with zipfile.ZipFile(apk) as package:
        names = set(package.namelist())
        for name in ('assets/runtime.payload', 'assets/runtime.sha256',
                     'lib/arm64-v8a/libfxdisplay.so', 'lib/arm64-v8a/libfxio.so'):
            if name not in names:
                raise ApkError('package: missing %s' % name)
        if any(fragment in name for name in names
               for fragment in ('eboot.bin', 'sce_module', 'sce_sys', 'boot-linked.bin')):
            raise ApkError('package: forbidden game content')
        payload = package.read('assets/runtime.payload')
        declared = package.read('assets/runtime.sha256').decode('ascii').strip()
        actual = hashlib.sha256(payload).hexdigest()
        if declared != actual:
            raise ApkError('checksum: APK payload digest mismatch')
        dex = b''.join(package.read(name) for name in sorted(names)
                       if name.startswith('classes') and name.endswith('.dex'))
        if b'ro/cobrabm/fexdroid' not in dex:
            raise ApkError('metadata: expected Java package is absent from DEX')
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / 'runtime.tar.gz'
            digest = Path(directory) / 'runtime.sha256'
            archive.write_bytes(payload)
            digest.write_text(declared + '\n')
            try:
                validate_archive(archive, digest, manifest)
            except ArchiveError as error:
                text = str(error)
                category = 'interpreter' if 'interpreter' in text or 'loader' in text else 'archive completeness'
                raise ApkError('%s: %s' % (category, text)) from error
    badging = _badging(apk, aapt)
    if badging:
        package_match = re.search(r"package: name='([^']+)'", badging)
        if not package_match or package_match.group(1) != 'com.gow3.android':
            raise ApkError('metadata: application id is not com.gow3.android')
        if "targetSdkVersion:'28'" not in badging:
            raise ApkError('metadata: target SDK is not 28')
        if 'application-debuggable' in badging and not allow_debuggable:
            raise ApkError('metadata: release APK is debuggable')
    return {'apk': str(apk), 'payload_sha256': actual, 'application_id': 'com.gow3.android'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk', type=Path)
    parser.add_argument('--aapt')
    parser.add_argument('--allow-debuggable', action='store_true')
    parser.add_argument('--manifest', type=Path)
    args = parser.parse_args(argv)
    try:
        print(validate_apk(args.apk, args.aapt, args.allow_debuggable, args.manifest))
    except (OSError, zipfile.BadZipFile, ApkError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
