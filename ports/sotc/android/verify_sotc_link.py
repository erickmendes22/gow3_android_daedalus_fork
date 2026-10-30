#!/usr/bin/env python3
"""Verify the actual SotC Vulkan DSO resolves its runtime_* imports in FEX's PIE.

A successfully linked ELF is not enough: Android dlopen(RTLD_NOW) needs every
strong HLE import from the main executable or a declared shared dependency.
"""
import argparse
from pathlib import Path
import re
import subprocess

EXPORTS={'bbgpu_init','bbgpu_resolve','bbgpu_register_kernel',
         'bbgpu_handle_fault','bbgpu_symbol_count'}
ALLOWED={'libc.so','libm.so','libdl.so','liblog.so','libandroid.so',
         'libnativewindow.so','libc++_shared.so','libvulkan.so','libz.so','libatomic.so'}

def run(*args):
    return subprocess.check_output(args,text=True)

def dynamic_symbols(text,defined):
    result=set()
    for line in text.splitlines():
        cols=line.split()
        if len(cols)<2: continue
        if defined:
            if len(cols)<3 or cols[-2].upper() not in {'T','D','B','R','W','V'}: continue
        elif cols[-2] != 'U':
            continue
        result.add(cols[-1].split('@')[0])
    return result

def verify(tc,renderer,probe):
    nm=tc/'bin/llvm-nm'
    readelf=tc/'bin/llvm-readelf'
    if not renderer.is_file() or not probe.is_file():
        raise ValueError('Built SotC renderer and FEX probe must both exist')
    for f in (renderer,probe):
        h=run(str(readelf),'-h',str(f))
        if 'AArch64' not in h:
            raise ValueError(f'Not AArch64: {f}')
    needed=set(re.findall(r'NEEDED.*?\[(.*?)\]',run(str(readelf),'-d',str(renderer))))
    extra=needed-ALLOWED
    if extra:
        raise ValueError(f'Unexpected SotC Android DSO dependencies: {sorted(extra)}')
    defined=dynamic_symbols(run(str(nm),'-D','--defined-only',str(renderer)),True)
    missing_exports=EXPORTS-defined
    if missing_exports:
        raise ValueError(f'SotC renderer C ABI exports missing: {sorted(missing_exports)}')
    undefined=dynamic_symbols(run(str(nm),'-D','--undefined-only',str(renderer)),False)
    probe_exports=dynamic_symbols(run(str(nm),'-D','--defined-only',str(probe)),True)
    missing_runtime={name for name in undefined if name.startswith('runtime_') and name not in probe_exports}
    if missing_runtime:
        raise ValueError('Unresolved FEX main-executable HLE symbols: '+', '.join(sorted(missing_runtime)))
    other={name for name in undefined if name.startswith(('bbgpu_','sotc_')) and name not in probe_exports}
    if other:
        raise ValueError('Unresolved SotC-specific symbols: '+', '.join(sorted(other)))
    print(f'SotC DSO ABI verified: {len(defined)} exported symbols; '
          f'{len(undefined & probe_exports)} imports from FEX executable; '
          f'NEEDED={sorted(needed)}')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ndk',type=Path,required=True)
    p.add_argument('--renderer',type=Path,required=True)
    p.add_argument('--probe',type=Path,required=True)
    a=p.parse_args()
    try:
        verify(a.ndk/'toolchains/llvm/prebuilt/linux-x86_64',
               a.renderer,a.probe)
    except (OSError,ValueError,subprocess.CalledProcessError) as e:
        p.exit(1,'SotC binary ABI validation failed: '+str(e)+'\n')
if __name__=='__main__': main()
