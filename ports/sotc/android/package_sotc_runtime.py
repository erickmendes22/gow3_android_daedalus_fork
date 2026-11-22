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
        original=ROOT/'ports/sotc/android'
        strict_aot=os.environ.get('SOTC_REQUIRE_ON_DEVICE_AOT')=='1'
        if strict_aot:
            # The generic Bionic stage is FEX-backed; never ship its CPU.
            cpu_dir=Path(os.environ.get('SOTC_AOT_CPU_DIR',str(ROOT/'out/sotc-arm64-aot')))
            for name in ('libgow3cpu.so','libbbcpu.so'):
                source=cpu_dir/name
                if not source.is_file():
                    raise SystemExit('Strict AOT CPU library missing: '+str(source))
                shutil.copy2(source,libs/name)
            (libs/'libSotcAot.so').unlink(missing_ok=True)
            config=stage/'home/sotcport/.fex-emu'
            if config.is_dir(): shutil.rmtree(config)
            print('SotC: FEX CPU replaced with native ARM64 AOT')
        # The AOT CPU engine was linked with a newer Android NDK. Never ship
        # the GoW3/FEX-era libc++_shared.so unchanged: the on-device loader
        # fails before the game even starts (missing std::__hash_memory).
        libcxx_candidate=os.environ.get('SOTC_AOT_LIBCXX_SHARED','')
        if libcxx_candidate or os.environ.get('SOTC_REQUIRE_ON_DEVICE_AOT')=='1':
            cxx=Path(libcxx_candidate) if libcxx_candidate else (
                args.ndk.resolve()/'toolchains/llvm/prebuilt/linux-x86_64/sysroot/usr/lib'
                /'aarch64-linux-android/libc++_shared.so')
            if not cxx.is_file():
                raise SystemExit('AOT-matching libc++_shared.so missing: '+str(cxx))
            readelf=args.ndk.resolve()/'toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-readelf'
            subprocess.run(['python3',str(original/'aot/verify_libcxx_abi.py'),
                            '--old',str(libs/'libc++_shared.so'),
                            '--new',str(cxx),
                            '--cpu',str(libs/'libgow3cpu.so'),
                            '--readelf',str(readelf)],check=True)
            shutil.copy2(cxx,libs/'libc++_shared.so')
            # Keep the compiled dynamic symbol table, remove only debug data.
            strip=args.ndk.resolve()/'toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-strip'
            subprocess.run([str(strip),'--strip-unneeded',str(libs/'libc++_shared.so')],check=True)
        scripts=base/'scripts'
        notices=base/'licenses'
        target=libs/'libbbgpu.so'
        shutil.copy2(renderer,target)
        strip=args.ndk.resolve()/'toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-strip'
        subprocess.run([str(strip),'--strip-unneeded',str(target)],check=True)
        shutil.copy2(original/'run-sotc-bionic.sh',base/'run-sotc-bionic.sh')
        (base/'run-sotc-bionic.sh').chmod(0o755)
        shutil.copy2(original/'prepare_game.py',scripts/'sotc_prepare_game.py')
        shutil.copy2(original/'bachata_perf.py',scripts/'bachata_perf.py')
        # SotC on-device ARM64 recompilation is opt-in and self-contained.
        # Only the official pinned bb-recomp toolchain enters the APK; the
        # proprietary game image is reconstructed on the user's device.
        aot=original/'aot'
        shutil.copy2(aot/'compile_local.py',scripts/'sotc_aot_compile.py')
        shutil.copy2(aot/'cmdline_image.py',scripts/'cmdline_image.py')
        shutil.copy2(aot/'select_local_aot.py',scripts/'sotc_aot_select.py')
        shutil.copy2(aot/'verify_compiler.py',scripts/'sotc_aot_verify_compiler.py')
        compiler_archive=os.environ.get('SOTC_AOT_COMPILER_TAR','')
        if compiler_archive:
            from aot.stage_on_device_compiler import stage as stage_aot_compiler
            result=stage_aot_compiler(Path(compiler_archive),base)
            print('SotC on-device AOT toolchain:',result)
        elif os.environ.get('SOTC_REQUIRE_ON_DEVICE_AOT')=='1':
            raise SystemExit('AOT compiler archive missing: SOTC_AOT_COMPILER_TAR')
        if strict_aot:
            # The official archive supplies the ABI-2 helper bundle ONLY. The
            # old official bb-recomp has 10 fatal traps on SotC and must not
            # appear as a runnable fallback anywhere in the strict runtime.
            patched=Path(os.environ.get('SOTC_AOT_PATCHED_COMPILER',''))
            if not patched.is_file():
                raise SystemExit('Strict AOT requires patched Android compiler: SOTC_AOT_PATCHED_COMPILER')
            binary=patched.read_bytes()
            if len(binary)<4096 or binary[:4]!=b'\x7fELF' or int.from_bytes(binary[18:20],'little')!=183:
                raise SystemExit('SotC patched AOT compiler must be AArch64 ELF PIE')
            marker=b'SOTC_AOT_MASKED_SSE42_JTRODATA_NO_TSO_2'
            if marker not in binary:
                raise SystemExit('SotC patched compiler lacks native SIMD/SSE4.2 code marker')
            patched_sha=hashlib.sha256(binary).hexdigest()
            jni=ROOT/'out/bionic/apk-jni/arm64-v8a/libbbrecomp.so'
            jni.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(patched,jni)
            # APP nativeLibraryDir is executable under Android W^X.
            # Do not store an extra 53-MB stock compiler in the runtime.
            (base/'arm64/aot/bin/libbbrecomp.so').unlink(missing_ok=True)
            digest=base/'arm64/aot/sotc-patched-compiler.sha256'
            digest.write_text(patched_sha+'  libbbrecomp.so\n')
            print('Strict SotC patched AOT SHA256:',patched_sha)

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
        # BBPROBE5 uses guest_cpu_*; strict AOT installs the native ABI engine
        # and never ships the original FEX CPU implementation.
        if (base/'patches').is_dir(): shutil.rmtree(base/'patches')
        for legacy in ('run-bionic.sh','gow3.ini','gow3.default.ini'):
            (base/legacy).unlink(missing_ok=True)
        for entry in scripts.iterdir():
            if entry.name not in ('sotc_prepare_game.py','bachata_perf.py','sotc-upstream',
                                   'sotc_aot_compile.py','sotc_aot_select.py',
                                   'cmdline_image.py','sotc_aot_verify_compiler.py'):
                if entry.is_dir(): shutil.rmtree(entry)
                else: entry.unlink()
        (base/'arm64/bin/gow3-probe').rename(base/'arm64/bin/sotc-probe')
        fex=stage/'home/sotcport/.fex-emu/bb-probe.json'
        if fex.exists(): fex.rename(fex.with_name('sotc-probe.json'))
        defaults='''# Shadow of the Colossus Android/Bionic
sotc_resolution=720p
sotc_fps_mode=fps60game
sotc_vsync=1
sotc_readbacks=2
sotc_rb_stream=1
sotc_af16=0
sotc_blur_suppression=1
sotc_fast_bind=1
sotc_stage_spec_memo=1
sotc_stage_snapshot_swap=1
sotc_reg_snapshot_memo=1
sotc_rt_memo=1
sotc_rb_hot=0
sotc_pc072_fast_readbacks_050=0
sotc_staging_large_pow2=1
sotc_staging_large_keep_mb=128
sotc_buf_async_kb=256
sotc_fill_hle_gpu=1
sotc_tex_async_kb=512
sotc_show_fps=1
sotc_vm_range_cache=1
sotc_perf_profile=0
sotc_async_shaders=1
sotc_async_compute=1
sotc_present_full_blit=1
sotc_pipeline_bind_memo=1
sotc_vertex_input_memo=1
sotc_descriptor_slot_reuse=1
sotc_record_thread=1
sotc_rb_async=1
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
                        runtime_name='sotc-daedalus-aot-0.1.70' if strict_aot else 'sotc-daedalus-bionic-0.1.53',
                        version='0.1.70-gamehub-ui' if strict_aot else '0.1.53-boot-test',
                        game='Shadow of the Colossus',
                        gamehub_dd_turnip_bundled=driver_included)
        identity.update(aot_mode='strict' if strict_aot else 'not-integrated',
                        fex_runtime_included=not strict_aot,
                        on_device_aot_compiler_included=bool(compiler_archive))
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
