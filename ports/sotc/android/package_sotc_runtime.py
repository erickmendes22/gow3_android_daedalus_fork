#!/usr/bin/env python3
"""Package separate SotC Android Bionic test runtime without Sony/game assets.

Reuses the validated GoW3 FEX/Bionic toolchain and Android present protocol,
then adds the original SotC renderer and preparation scripts.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import os
from vendor_turnip import embed_verified_turnip, ARCHIVE_RELATIVE

ROOT=Path(__file__).resolve().parents[3]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ndk',type=Path,required=True)
    p.add_argument('--upstream',type=Path,required=True)
    p.add_argument('--renderer',type=Path,required=True)
    args=p.parse_args()
    upstream=args.upstream.resolve()
    renderer=args.renderer.resolve()
    if not (upstream/'scripts/prepare.py').is_file():
        p.error('Pinned ShadowOfTheColossus-PC checkout missing')
    if not renderer.is_file():
        p.error('Actual libbbgpu.so must build before any SotC APK is packaged')
    # Preserve the existing Bionic runtime, Python, drivers, FEX, launcher
    # protocol and all required license notices. Never repackage game data.
    subprocess.run(['python3',str(ROOT/'tools/android/bionic/package_runtime.py'),
                    '--ndk',str(args.ndk.resolve())],check=True)
    archive=ROOT/'out/release/runtime.tar.gz'
    with tempfile.TemporaryDirectory(prefix='sotc-bionic-package-') as tmp:
        stage=Path(tmp)/'stage'
        stage.mkdir()
        with tarfile.open(archive,'r:gz') as tar:
            tar.extractall(stage,filter='data')
        base=stage/'sotcport'
        (stage/'gow3port').rename(base)
        (stage/'home/gow3port').rename(stage/'home/sotcport')
        libs=base/'arm64/lib'
        scripts=base/'scripts'
        notices=base/'licenses'
        target=libs/'libbbgpu.so'
        shutil.copy2(renderer,target)
        strip=args.ndk.resolve()/'toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-strip'
        subprocess.run([str(strip),'--strip-unneeded',str(target)],check=True)
        original=ROOT/'ports/sotc/android'
        shutil.copy2(original/'run-sotc-bionic.sh',base/'run-sotc-bionic.sh')
        (base/'run-sotc-bionic.sh').chmod(0o755)
        shutil.copy2(original/'prepare_game.py',scripts/'sotc_prepare_game.py')
        shutil.copy2(original/'bachata_perf.py',scripts/'bachata_perf.py')
        shutil.copytree(upstream/'scripts',scripts/'sotc-upstream/scripts',
                        ignore=shutil.ignore_patterns('__pycache__'))
        # Patch the real pinned SotC scripts *inside the packaged payload*.
        # Merely changing the launcher resolution list cannot fix 540p:
        # the original render_patches() rejects height 540 (modulo 8).
        from stage_sotc_lowres import patch_sotc_lowres_modes
        patch_sotc_lowres_modes(scripts/'sotc-upstream/scripts/sotc_modes.py')
        shutil.copy2(upstream/'LICENSE',notices/'LICENSE-ShadowOfTheColossus-PC.txt')
        # Optional, hash-pinned user-provided Android HAL Turnip. Never substitute
        # another binary. The normal Gen8/custom/system choices remain present.
        vendor_zip=Path(os.environ.get('SOTC_GAMEHUB_TURNIP_ZIP', str(ROOT/ARCHIVE_RELATIVE)))
        driver_included=embed_verified_turnip(stage,vendor_zip)
        # Never label an APK as containing the experimental GameHub DD binary
        # if the exact user-provided archive was not present during packaging.
        if os.environ.get("SOTC_REQUIRE_GAMEHUB_DD") == "1" and not driver_included:
            raise SystemExit(
                "SotC GameHub DD Turnip required but missing. Put the exact ZIP at "
                +str(ROOT/ARCHIVE_RELATIVE)
            )
        # No GoW3 game patches, cheats, launcher, or resolution config in SotC.
        # Existing FEX and native ABI libraries remain because the BBPROBE5
        # executable still links against their shared low-level interfaces.
        if (base/'patches').is_dir(): shutil.rmtree(base/'patches')
        for legacy in ('run-bionic.sh','gow3.ini','gow3.default.ini'):
            (base/legacy).unlink(missing_ok=True)
        for entry in scripts.iterdir():
            if entry.name not in ('sotc_prepare_game.py','bachata_perf.py','sotc-upstream'):
                if entry.is_dir(): shutil.rmtree(entry)
                else: entry.unlink()
        (base/'arm64/bin/gow3-probe').rename(base/'arm64/bin/sotc-probe')
        fex=stage/'home/sotcport/.fex-emu/bb-probe.json'
        if fex.exists(): fex.rename(fex.with_name('sotc-probe.json'))
        defaults='''# Shadow of the Colossus Android/Bionic
sotc_resolution=720p
sotc_fps_mode=fps60game
sotc_vsync=1
sotc_af16=0
sotc_blur_suppression=1
sotc_fast_bind=0
sotc_stage_spec_memo=1
sotc_stage_snapshot_swap=1
sotc_perf_profile=0
sotc_async_shaders=0
sotc_async_compute=0
sotc_present_full_blit=1
sotc_pipeline_bind_memo=1
sotc_vertex_input_memo=1
sotc_descriptor_slot_reuse=1
sotc_record_thread=0
sotc_rb_async=0
sotc_bachata_bloom=1
sotc_bachata_ssr=0
sotc_bachata_fog=0
sotc_bachata_shadows=0
android_fullscreen=0
'''
        (base/'sotc.default.ini').write_text(defaults)
        (base/'sotc.ini').write_text(defaults)
        manifest_path=stage/'runtime-manifest.json'
        identity=json.loads(manifest_path.read_text())
        identity.update(application_id='com.sotc.android.daedalus',
                        runtime_name='sotc-daedalus-bionic-0.1.30',
                        version='0.1.30-boot-test',
                        game='Shadow of the Colossus',
                        gamehub_dd_turnip_bundled=driver_included)
        manifest_path.write_text(json.dumps(identity,indent=2)+'\n')
        output=ROOT/'out/release/sotc-runtime.tar.gz'
        with tarfile.open(output,'w:gz',compresslevel=6) as tar:
            for item in sorted(stage.iterdir()):
                tar.add(item,arcname=item.name)
        sha=hashlib.sha256(output.read_bytes()).hexdigest()
        assets=ROOT/'out/android-release/assets'
        assets.mkdir(parents=True,exist_ok=True)
        shutil.copy2(output,assets/'runtime.payload')
        (assets/'runtime.sha256').write_text(sha+'\n')
        print(f'SotC Android Bionic payload: {output}, SHA-256 {sha}')

if __name__=='__main__':
    main()
