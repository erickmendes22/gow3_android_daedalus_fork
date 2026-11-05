#!/usr/bin/env python3
"""Extract the allow-listed ARM64 fexdroid bridge libraries from an APK."""
import argparse
import hashlib
import json
import struct
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ALLOW = {
    'lib/arm64-v8a/libfxdisplay.so': 'libfxdisplay.so',
    'lib/arm64-v8a/libfxio.so': 'libfxio.so',
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_elf(data, name):
    if data[:4] != b'\x7fELF' or data[4] != 2 or data[5] != 1:
        raise SystemExit(f'{name}: expected little-endian ELF64')
    if struct.unpack_from('<H', data, 18)[0] != 183:
        raise SystemExit(f'{name}: expected AArch64 ELF machine')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk', type=Path)
    parser.add_argument('--out', type=Path,
                        default=ROOT / 'tools/android/bridges/arm64-v8a')
    parser.add_argument('--metadata', type=Path,
                        default=ROOT / 'tools/android/bridges/provenance.json')
    args = parser.parse_args()
    if not args.apk.is_file():
        raise SystemExit(f'bridge APK does not exist: {args.apk}')
    args.out.mkdir(parents=True, exist_ok=True)
    records = []
    with zipfile.ZipFile(args.apk) as archive:
        names = set(archive.namelist())
        for archive_name, output_name in ALLOW.items():
            if archive_name not in names:
                raise SystemExit(f'missing allow-listed bridge: {archive_name}')
            data = archive.read(archive_name)
            verify_elf(data, archive_name)
            output = args.out / output_name
            output.write_bytes(data)
            try:
                output_name_for_metadata = str(output.relative_to(ROOT))
            except ValueError:
                output_name_for_metadata = str(output.resolve())
            records.append({
                'archive_path': archive_name,
                'output_path': output_name_for_metadata,
                'sha256': digest(output),
                'size': len(data),
            })
    metadata = {
        'schema_version': 1,
        'source_apk': args.apk.name,
        'source_apk_sha256': digest(args.apk),
        'source_project': 'fexdroid',
        'source_revision': '2b03ec73c3507b640fba1942fb8d99b43b88945a',
        'abi': 'arm64-v8a',
        'license': 'fexdroid upstream license; see frontend/THIRD_PARTY_LICENSES.txt',
        'distribution': 'developer-provided extracted bridge inputs; verify upstream license before redistribution',
        'files': records,
    }
    args.metadata.parent.mkdir(parents=True, exist_ok=True)
    args.metadata.write_text(json.dumps(metadata, indent=2) + '\n')
    print(json.dumps(metadata, indent=2))


if __name__ == '__main__':
    main()
