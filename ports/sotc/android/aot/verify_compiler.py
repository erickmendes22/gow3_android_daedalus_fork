#!/usr/bin/env python3
"""Verify the Android ARM64 bb-recomp compiler without mksh here-doc temp files.

Android mksh sometimes puts here-document scratch data under /data/local,
which a normal app cannot write. Read the SHA256 manifest as an ordinary file.
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path

MARKER = b'SOTC_AOT_MASKED_SSE42_JTRODATA_NO_TSO_2'

def verify_compiler(compiler: Path, manifest: Path) -> dict:
    expected = manifest.read_text(encoding='utf-8').split()[0]
    if len(expected) != 64 or any(ch not in '0123456789abcdef' for ch in expected):
        raise ValueError('Invalid SotC patched compiler SHA256 manifest')
    digest = hashlib.sha256()
    marker_found = False
    prior = b''
    with compiler.open('rb') as f:
        elf = f.read(20)
        if (len(elf) != 20 or elf[:4] != b'\x7fELF' or elf[4] != 2
                or int.from_bytes(elf[16:18], 'little') != 3
                or int.from_bytes(elf[18:20], 'little') != 183):
            raise ValueError('Patched SotC compiler must be 64-bit AArch64 ELF PIE')
        digest.update(elf)
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            if MARKER in (prior + chunk):
                marker_found = True
            prior = chunk[-len(MARKER) + 1:]
            digest.update(chunk)
    if not marker_found:
        raise ValueError('Wrong compiler binary: patched SIMD/SSE4.2 marker missing')
    if digest.hexdigest() != expected:
        raise ValueError('Patched SotC compiler SHA256 differs from packaged manifest')
    return {'status': 'verified', 'arch': 'AArch64', 'sha256': expected,
            'patched_masked_sse42': True, 'tso': False}

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--compiler', type=Path, required=True)
    p.add_argument('--manifest', type=Path, required=True)
    a = p.parse_args()
    try:
        result = verify_compiler(a.compiler, a.manifest)
    except (OSError, ValueError, IndexError) as e:
        print(f'SotC AOT compiler verification failed: {e}', flush=True)
        return 4
    print('SotC AOT patched ARM64 compiler verified: ' + result['sha256'], flush=True)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
