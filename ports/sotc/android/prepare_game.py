#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Prepare a personal PS4 SotC dump for Android using AjncSystem's original scripts.

The output requires a SotC-specific Bionic+FEX runtime. It is not an APK.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

SUPPORTED={'CUSA08809':'EU 1.01','CUSA08034':'US 1.00'}
SCRIPTS=('prepare.py','link_modules.py','content_profile.py','sotc_cpu.py','sotc_modes.py')
OUTPUTS=('boot-linked.bin','content.bin','sotc-cpu.bin','patches.bin')
SOUND_MODULES=('libSceNgs2.sprx','libSceUlt.sprx')

def sfo_title_id(path):
    data=path.read_bytes()
    if len(data)<20 or data[:4]!=b'\x00PSF':
        raise ValueError('Invalid param.sfo')
    keys,values,count=struct.unpack_from('<III',data,8)
    if count>1024 or 20+count*16>len(data):
        raise ValueError('Invalid SFO index')
    for i in range(count):
        keyoff,fmt,size,_max,off=struct.unpack_from('<HHIII',data,20+i*16)
        start=keys+keyoff
        if start>=len(data):
            raise ValueError('SFO key out of range')
        end=data.find(b'\x00',start)
        if end<0:
            raise ValueError('Unterminated SFO key')
        if data[start:end]!=b'TITLE_ID':
            continue
        start=values+off
        if not size or start>len(data) or size>len(data)-start or fmt==0x404:
            raise ValueError('Invalid TITLE_ID')
        return data[start:start+size].rstrip(b'\x00').decode('ascii')
    raise ValueError('TITLE_ID missing')

def fingerprint(paths):
    digest=hashlib.sha256(b'sotc-android-prepare-v1\n')
    for p in sorted(set(x.resolve() for x in paths)):
        stat=p.stat()
        digest.update(str(p).encode())
        digest.update(struct.pack('<QQ',stat.st_size,stat.st_mtime_ns&((1<<64)-1)))
        with p.open('rb') as f:
            digest.update(f.read(65536))
    return digest.hexdigest()

def prepare(upstream,game,out,sys_modules=None,modes='fps60game',
            render='1280x720',cvars='',force=False):
    upstream,game,out=(Path(p).resolve() for p in (upstream,game,out))
    if out==game or game in out.parents:
        raise ValueError('Do not write generated files into the game dump')
    for name in SCRIPTS:
        if not (upstream/'scripts'/name).is_file():
            raise FileNotFoundError('Missing upstream script: '+name)
    eboot=game/'eboot.bin'
    sfo=game/'sce_sys/param.sfo'
    if not eboot.is_file() or not sfo.is_file():
        raise FileNotFoundError('Dump must contain eboot.bin and sce_sys/param.sfo')
    with eboot.open('rb') as f:
        magic=f.read(4)
    if magic not in (b'O\x15=\x1d',b'\x7fELF'):
        raise ValueError('Expected plaintext PS4 SELF or ELF')
    title=sfo_title_id(sfo)
    if title not in SUPPORTED:
        raise ValueError('Unsupported SotC game: '+title)
    extras=[]
    if sys_modules:
        sys_modules=Path(sys_modules).resolve()
        extras=[sys_modules/name for name in SOUND_MODULES]
        for p in extras:
            if not p.is_file():
                raise FileNotFoundError('Personal audio module missing: '+p.name)
    out.mkdir(parents=True,exist_ok=True)
    inputs=[eboot,sfo,*sorted((game/'sce_module').glob('*.prx')),*extras,
            *(upstream/'scripts'/name for name in SCRIPTS)]
    fp=fingerprint(inputs)
    stamp=out/'.sotc-android-prepare.json'
    try:
        cached=json.loads(stamp.read_text())
    except (ValueError,OSError):
        cached={}
    current=cached.get('fingerprint')==fp and all((out/name).is_file() for name in OUTPUTS[:3])

    def run(name,*args):
        cmd=[sys.executable,str(upstream/'scripts'/name),str(game),
             '--out',str(out),*map(str,args)]
        subprocess.run(cmd,cwd=upstream/'scripts',check=True)

    if force or not current:
        run('prepare.py')
        args=['--sys-modules',str(sys_modules)] if sys_modules else []
        run('link_modules.py',*args)
        run('content_profile.py')
        run('sotc_cpu.py')
        stamp.write_text(json.dumps({'fingerprint':fp,'title_id':title})+'\n')
    modeargs=['--modes',modes,'--cvars',cvars]
    if render and render!='1920x1080':
        modeargs+=['--render',render]
    run('sotc_modes.py',*modeargs)
    for name in OUTPUTS:
        if not (out/name).is_file():
            raise RuntimeError('Upstream output missing: '+name)
    return {
      'title_id':title,'version':SUPPORTED[title],
      'image':str(out/'boot-linked.bin'),'content':str(out/'content.bin'),
      'sotc_cpu':str(out/'sotc-cpu.bin'),'patches':str(out/'patches.bin'),
      'cmdline':str(out/'cmdline.bin') if (out/'cmdline.bin').is_file() else None,
      'cached':current and not force,'audio':bool(extras),
      'requires':'SotC-specific Bionic/FEX native runtime (not yet integrated)'
    }

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--upstream',type=Path,required=True)
    p.add_argument('--game-dir',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--sys-modules',type=Path)
    p.add_argument('--modes',default='fps60game')
    p.add_argument('--render',default='1280x720')
    p.add_argument('--cvars',default='doIndexBufferCulling=0 doSunShadowIndexBufferCulling=0')
    p.add_argument('--force',action='store_true')
    a=p.parse_args()
    try:
        result=prepare(a.upstream,a.game_dir,a.out,a.sys_modules,a.modes,
                       a.render,a.cvars,a.force)
    except (OSError,ValueError,subprocess.CalledProcessError,RuntimeError) as e:
        p.exit(1,'SotC preparation failed: '+str(e)+'\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':
    main()
