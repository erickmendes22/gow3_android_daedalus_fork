#!/usr/bin/env python3
"""Reconstruct the UB2 AOT runtime from SHA-pinned public generic tools.
Never includes a signing key, game data or precompiled guest code.
Run stage_ubo_runtime.py first to preserve the verified GoW3 baseline.
"""
import hashlib
import io
import re
import struct
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ASSETS = ROOT / 'out/android-release/assets'
ARM = 'gow3port/arm64/'
DONOR_HASH = '7a06c68cc005c3855f176458dce88d216ab63dd47f5f0be147e7452578fe15e6'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def elf(data):
    return data[:6] == b'\x7fELF\x02\x01' and struct.unpack_from('<H', data, 18)[0] == 183

def symbols(path):
    table = subprocess.check_output(['readelf', '--dyn-syms', '-W', str(path)], text=True)
    return [(m[1], m[2], m[3]) for m in re.finditer(
        r'^\s*\d+:\s+\w+\s+\d+\s+\w+\s+(\w+)\s+\w+\s+(\w+)\s+([^@\s]+)', table, re.M)]

def main():
    donor, probe, baseline = map(Path, sys.argv[1:4])
    assert sha(donor.read_bytes()) == DONOR_HASH
    with zipfile.ZipFile(donor) as src, zipfile.ZipFile(io.BytesIO(src.read('assets/tools.zip'))) as tools:
        compiler = tools.read('bin/libbbrecomp.so')
        assert b'3-tlou-string' in compiler and elf(compiler)
        add = {
            ARM+'aot/bin/libbbrecomp.so': (compiler, 0o755),
            ARM+'aot/upstream.sha256': (tools.read('aot/upstream.sha256'), 0o644),
            'gow3port/scripts/aot_local.py': ((ROOT/'scripts/aot_local.py').read_bytes(), 0o644),
        }
        for name in ('helpers-aarch64.o', 'libbbcpu-stub.so', 'libclang_rt.builtins-aarch64-android.a', 'libm.so'):
            add[ARM+'aot/bundle/'+name] = (tools.read('aot/bundle/'+name), 0o644)
        for name in ('libbbcpu.so', 'libgow3cpu.so'):
            add[ARM+'aot/backend/'+name] = (src.read('assets/runtime-aot/'+name), 0o755)
        for name in tools.namelist():
            if name.startswith('aot/licenses/') and not name.endswith('/'):
                add['gow3port/licenses/bbrecomp/'+Path(name).name] = (tools.read(name), 0o644)
        add['gow3port/licenses/bbrecomp/GoW3-integration.txt'] = (
            b'Local compiler: TLOU Android modified compiler (3-tlou-string).\n'
            b'Original tool by ducvd89, GPL-3.0-or-later.\n'
            b'https://github.com/ducvd89/Bloodborne-android-rebuild-tool\n'
            b'https://github.com/erickmendes22/tlou-remastered-android\n'
            b'Generic compiler and backend only; no game code is distributed.\n', 0o644)
    payload = ASSETS/'runtime.payload'
    assert sha(payload.read_bytes()) == (ASSETS/'runtime.sha256').read_text().strip()
    new_probe = probe.read_bytes()
    assert elf(new_probe)
    with tarfile.open(payload, 'r:gz') as old, tempfile.TemporaryDirectory() as tmp:
        gpu = old.extractfile(ARM+'lib/libgow3gpu.so').read()
        with zipfile.ZipFile(baseline) as src, tarfile.open(fileobj=io.BytesIO(src.read('assets/runtime.payload')), mode='r:gz') as orig:
            old_gpu = orig.extractfile(ARM+'lib/libgow3gpu.so').read()
        items = {
            'cpu-fex': old.extractfile(ARM+'lib/libgow3cpu.so').read(),
            'cpu-aot': add[ARM+'aot/backend/libgow3cpu.so'][0],
            'cpu-alias': add[ARM+'aot/backend/libbbcpu.so'][0],
            'libc++': old.extractfile(ARM+'lib/libc++_shared.so').read(),
            'gpu-reference': old_gpu, 'probe': new_probe, 'gpu': gpu, 'compiler': compiler,
        }
        tables = {}
        for name, data in items.items():
            assert elf(data), name
            path = Path(tmp)/name
            path.write_bytes(data)
            tables[name] = symbols(path)
        provided = lambda name: {sym for _, ndx, sym in tables[name] if ndx != 'UND'}
        needed = lambda name: {sym for bind, ndx, sym in tables[name] if ndx == 'UND' and bind == 'GLOBAL'}
        runtime_api = {s for s in needed('gpu') if s.startswith('runtime_')}
        assert runtime_api <= provided('probe'), sorted(runtime_api-provided('probe'))
        gpu_api = needed('probe') & provided('gpu-reference')
        assert gpu_api <= provided('gpu'), sorted(gpu_api-provided('gpu'))
        engine = {s for s in needed('probe')|needed('gpu') if s.startswith('guest_cpu_')}
        for backend in ('cpu-fex','cpu-aot'):
            assert engine <= provided(backend), sorted(engine-provided(backend))
        for obj in ('cpu-aot','gpu','probe'):
            cpp = {s for s in needed(obj) if '__ndk1' in s}
            exports = provided('probe')|provided('gpu')|provided('libc++')
            assert cpp <= exports, (obj, sorted(cpp-exports))
        alias = subprocess.check_output(['readelf','-dW',str(Path(tmp)/'cpu-alias')], text=True)
        assert '[libgow3cpu.so]' in alias
        assert b'Guest CPU: ahead-of-time units only' in items['cpu-aot']
        print(f'ELF ABI verified: {len(runtime_api)} runtime symbols; {len(engine)} shared FEX/AOT CPU symbols')
    output = payload.with_suffix('.new')
    found_probe = False
    with tarfile.open(payload,'r:gz') as old, tarfile.open(output,'w:gz',compresslevel=4) as out:
        for member in old:
            if member.name in add:
                # A future baseline may already contain aot_local.py.
                assert member.name == 'gow3port/scripts/aot_local.py', member.name
                data, mode = add.pop(member.name)
                member.size = len(data)
                member.mode = mode
                out.addfile(member, io.BytesIO(data))
            elif member.name == ARM+'bin/gow3-probe':
                found_probe = True
                member.size = len(new_probe)
                assert member.mode & 0o111
                out.addfile(member, io.BytesIO(new_probe))
            else:
                out.addfile(member, old.extractfile(member) if member.isfile() else None)
        for name, (data, mode) in add.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            member.mode = mode
            out.addfile(member, io.BytesIO(data))
    assert found_probe
    output.replace(payload)
    (ASSETS/'runtime.sha256').write_text(sha(payload.read_bytes())+'\n')
    jni = ROOT/'out/bionic/apk-jni/arm64-v8a'
    jni.mkdir(parents=True, exist_ok=True)
    (jni/'libbbrecomp.so').write_bytes(compiler)
    with tarfile.open(payload,'r:gz') as final:
        assert final.getmember(ARM+'aot/bin/libbbrecomp.so').mode & 0o111
        assert sha(final.extractfile(ARM+'aot/bin/libbbrecomp.so').read()) == sha(compiler)
    print('Staged complete UB2 FEX + AOT runtime with executable local compiler.')

if __name__ == '__main__':
    main()
