#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Compile a user's linked GoW III image locally for the Android AOT runtime."""
import argparse
from bisect import bisect_left
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import struct
import subprocess
import sys

from patches import CUSA01715_0102_ANDROID_SHA, REFERENCE_SHA256, patch_profile_status

BOOT = struct.Struct('<8s12Q')
PATCH = struct.Struct('<8sQQ')
FLAGS = ('--target', 'aarch64', '--host', 'armv8.2', '--resume-entries',
         '--no-callee-saved', '-O1', '--no-nice', '--progress', '--resume')
SUPPORTED = {'01.00': REFERENCE_SHA256, '01.02': CUSA01715_0102_ANDROID_SHA}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def checked_boot(path):
    with path.open('rb') as stream:
        magic, size, entry, segments, relocations, imports, caps, _, *tls = BOOT.unpack(
            stream.read(BOOT.size))
        modules = tls[-1]
        if (magic != b'G3PROBE5' or caps != 1 or not 0 < size <= 512 * 1024**2 or
                not 0 <= entry < size or not 0 < segments <= 64 or
                not 0 < modules <= 16 or imports > 100_000 or relocations > 1_000_000):
            raise ValueError('Unsupported linked GoW III image')
        stream.seek(BOOT.size + 56 * modules)
        bindings, = struct.unpack('<Q', stream.read(8))
        if bindings > imports:
            raise ValueError('Invalid linked bindings')
        stream.seek(24 * bindings, os.SEEK_CUR)
        spans = [struct.unpack('<3Q', stream.read(24)) for _ in range(segments)]
        if not any(start <= entry < start + length and flags & 1 for start, length, flags in spans):
            raise ValueError('Invalid linked entry')
        stream.seek(128 * imports, os.SEEK_CUR)
        reloc_start = stream.tell()
        image_start = reloc_start + 32 * relocations
        if path.stat().st_size != image_start + size:
            raise ValueError('Linked image length mismatch')
        return spans, image_start, reloc_start, relocations


def patched_boot(boot, patches, output):
    spans, image_start, reloc_start, relocations = checked_boot(boot)
    raw = patches.read_bytes()
    magic, base, count = PATCH.unpack_from(raw)
    if magic != b'G3PATCH2' or base != 0x400000 or count > 10000:
        raise ValueError('Unsupported GoW III patch table')
    cursor = PATCH.size
    records = []
    for _ in range(count):
        offset, size = struct.unpack_from('<2Q', raw, cursor)
        cursor += 16
        if (not 0 < size <= 4096 or cursor + size > len(raw) or
                not any(start <= offset and offset + size <= start + length
                        for start, length, _ in spans)):
            raise ValueError('Invalid AOT patch range')
        records.append((offset, raw[cursor:cursor + size]))
        cursor += size
    if cursor != len(raw):
        raise ValueError('Trailing GoW III patch data')

    # Retain the loader's rebasing for complete base-relative pointer writes.
    # Other patches directly change the same image that the compiler inspects.
    with boot.open('rb') as source:
        source.seek(reloc_start)
        raw_relocs = source.read(relocations * 32)
    ordered = sorted(struct.unpack_from('<Q', raw_relocs, i * 32)[0] for i in range(relocations))
    index = {struct.unpack_from('<Q', raw_relocs, off)[0]: off for off in range(0, len(raw_relocs), 32)}
    shutil.copyfile(boot, output)
    with output.open('r+b') as stream:
        for offset, data in records:
            first = bisect_left(ordered, max(offset - 7, 0))
            last = bisect_left(ordered, offset + len(data))
            for target in ordered[first:last]:
                reloc = index[target]
                _, kind, _, addend = struct.unpack_from('<4Q', raw_relocs, reloc)
                if kind or addend or not offset <= target <= offset + len(data) - 8:
                    raise ValueError('Patch overlaps an unsupported relocation')
                value, = struct.unpack_from('<Q', data, target - offset)
                relative = value - base
                if not any(start <= relative < start + length for start, length, _ in spans):
                    raise ValueError('Patched pointer outside the linked image')
                stream.seek(reloc_start + reloc + 16)
                stream.write(struct.pack('<Q', relative))
            stream.seek(image_start + offset)
            stream.write(data)


def verify_units(library, stats):
    with library.open('rb') as stream:
        elf = stream.read(20)
    if elf[:5] != b'\x7fELF\x02' or struct.unpack_from('<HH', elf, 16) != (3, 183):
        raise ValueError('AOT compiler did not produce an ARM64 shared library')
    meta = json.loads(library.with_suffix('.json').read_text())
    text = stats.read_text(encoding='utf-8', errors='replace')
    traps = re.search(r'units with bbr_trap \(unsupported ops\):\s*(\d+)', text)
    if (meta.get('abi_version') != 2 or meta.get('so_sha256') != digest(library) or
            int(meta.get('unit_count', 0)) <= 0 or not traps or
            'LoadMemTSO' in text or 'StoreMemTSO' in text):
        raise ValueError('Invalid AOT ABI, integrity or coverage report')
    if int(traps[1]):
        raise ValueError(f'AOT compiler left {traps[1]} units with unsupported instructions')
    return meta['unit_count']


def run_compiler(command, parent):
    if parent is None:
        subprocess.run(command, stdout=sys.stderr, stderr=sys.stderr, check=True)
        return
    if parent == 1 or os.getppid() != parent:
        raise OSError('AOT launcher is no longer running')
    with subprocess.Popen(command, stdout=sys.stderr, stderr=sys.stderr,
                          start_new_session=True) as compiler:
        while True:
            try:
                result = compiler.wait(timeout=0.5)
                if result:
                    raise subprocess.CalledProcessError(result, command)
                return
            except subprocess.TimeoutExpired:
                if os.getppid() == parent:
                    continue
                try:
                    os.killpg(compiler.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                compiler.wait()
                raise OSError('AOT compilation cancelled')


def compile_local(args):
    parent = os.getppid() if args.android else None
    identity = patch_profile_status(args.game)
    version = identity['app_version']
    if (identity['title_id'] not in {'CUSA01623', 'CUSA01715'} or
            version not in SUPPORTED or identity['eboot_sha256'] != SUPPORTED[version]):
        raise ValueError('AOT requires a verified CUSA01623/CUSA01715 01.00 or 01.02 executable')
    if args.game.resolve() in (args.out.resolve(), *args.out.resolve().parents):
        raise ValueError('AOT output must be outside the source game')
    compile_inputs = [args.boot, args.patches, args.compiler, *sorted(args.bundle.glob('*'))]
    key = hashlib.sha256(json.dumps([FLAGS, [digest(x) for x in compile_inputs]]).encode()).hexdigest()
    work = args.out / key
    work.mkdir(parents=True, exist_ok=True)
    library = work / 'libgow3aot.so'
    native = work / 'boot-native.bin'
    report = work / 'aot-report.json'
    stats = work / 'compile.txt'
    with (work / 'compile.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            recorded = json.loads(report.read_text())
            ready = (recorded['profile'] == key and recorded['boot_sha256'] == digest(native) and
                     recorded['library_sha256'] == digest(library))
        except (OSError, ValueError, KeyError):
            ready = False
        if not ready:
            report.unlink(missing_ok=True)
            patched_boot(args.boot, args.patches, native)
            bb_boot = work / 'compiler-input.bin'
            shutil.copyfile(native, bb_boot)
            with bb_boot.open('r+b') as stream:
                stream.write(b'BBPROBE5')
            print('AOT: compiling locally on Android, ARM64, TSO off', file=sys.stderr, flush=True)
            try:
                run_compiler([str(args.compiler), '--boot', str(bb_boot), '--game-dir', str(args.game),
                              '--so', str(library), '--stats', str(stats), '--bundle-dir', str(args.bundle),
                              '--jobs', '2', '--shards', '64', *FLAGS], parent)
                units = verify_units(library, stats)
                status = {'profile': key, 'revision': version, 'units': units, 'tso': 'off',
                          'boot_sha256': digest(native), 'library_sha256': digest(library)}
                tmp = report.with_suffix('.tmp')
                tmp.write_text(json.dumps(status) + '\n')
                tmp.replace(report)
            finally:
                bb_boot.unlink(missing_ok=True)
        print(work)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('game', 'boot', 'patches', 'out', 'compiler', 'bundle'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--android', action='store_true')
    args = parser.parse_args()
    try:
        compile_local(args)
    except (OSError, ValueError, struct.error, subprocess.SubprocessError) as error:
        print(f'AOT: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
