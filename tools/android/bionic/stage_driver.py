#!/usr/bin/env python3
"""Stage the exact user-supplied Bionic driver, locally or from its pinned release."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import urllib.request
import zipfile

MANIFEST = Path(__file__).with_name('driver.json')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def stage(archive, output, spec=None):
    spec = spec or json.loads(MANIFEST.read_text())
    data = Path(archive).read_bytes()
    if digest(data) != spec['archive_sha256']:
        raise ValueError('Driver ZIP SHA256 differs from the pinned driver build')
    with zipfile.ZipFile(archive) as z:
        # Do not extract paths from an archive into the filesystem.
        meta_bytes = z.read('meta.json')
        meta = json.loads(meta_bytes)
        if meta['libraryName'] != spec['library'] or meta['minApi'] != spec['min_api']:
            raise ValueError('Driver metadata differs from the pinned manifest')
        library = z.read(spec['library'])
    if digest(library) != spec['library_sha256']:
        raise ValueError('Driver library SHA256 mismatch')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        so = Path(tmp) / spec['library']
        so.write_bytes(library)
        header = subprocess.check_output(['readelf', '-h', str(so)], text=True)
        dynamic = subprocess.check_output(['readelf', '-d', str(so)], text=True)
        symbols = subprocess.check_output(['readelf', '--dyn-syms', '--wide', str(so)], text=True)
        if 'AArch64' not in header or 'ELF64' not in header or 'DYN ' not in header:
            raise ValueError('Expected an AArch64 shared library')
        if '[libc.so]' not in dynamic or '[libc.so.6]' in dynamic:
            raise ValueError('Expected Android Bionic, not Linux glibc')
        if not any(line.split()[-1:] == [spec['entry']] and ' UND ' not in line
                   for line in symbols.splitlines()):
            raise ValueError('Missing exported Vulkan HAL entry')
    (output / spec['library']).write_bytes(library)
    (output / 'meta.json').write_bytes(meta_bytes)
    (output / 'PINNED-DRIVER.json').write_text(json.dumps(spec, indent=2) + '\n')
    print(f"Staged {spec['name']}: {spec['library_sha256']}")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', type=Path, default=MANIFEST)
    p.add_argument('--archive', type=Path, help='Use the supplied ZIP instead of downloading')
    p.add_argument('--output', type=Path, default=Path('out/bionic-driver-check/drivers/gen8'))
    args = p.parse_args()
    spec = json.loads(args.manifest.read_text())
    if args.archive:
        stage(args.archive, args.output, spec)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / spec['archive']
            with urllib.request.urlopen(spec['url'], timeout=120) as response:
                archive.write_bytes(response.read())
            stage(archive, args.output, spec)


if __name__ == '__main__':
    main()
