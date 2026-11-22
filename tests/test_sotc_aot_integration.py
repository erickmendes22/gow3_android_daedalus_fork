#!/usr/bin/env python3
"""Release guards for the SotC native AOT launcher; no proprietary game bytes."""
from pathlib import Path
import importlib.util
import hashlib
import json
import struct
import tempfile
import unittest
R=Path(__file__).resolve().parents[1]

def source(name):
    return (R/name).read_text()

class SotcAotIntegrationGuards(unittest.TestCase):
    def test_no_fex_fallback_or_guest_code_in_public_apk(self):
        sh=source("ports/sotc/android/run-sotc-bionic.sh")
        self.assertIn('export BB_AOT="$base/user/aot/libSotcAot.so"',sh)
        self.assertIn('set -- "$probe" "$base/user/aot/boot-native.bin"',sh)
        self.assertIn('if [ ! -s "$base/user/aot/libSotcAot.so" ]',sh)
        self.assertIn("no verified local code",sh)
        self.assertNotIn('export BB_AOT="$runtime/lib/libSotcAot.so"',sh)
        self.assertNotIn('set -- "$probe" "$out/boot-linked.bin"',sh)
        self.assertNotIn('--patches "$out/patches.bin" \\',sh)
        self.assertNotIn('--sotc-cmdline "$out/cmdline.bin"',sh)
        self.assertNotIn('export FEX_APP_CONFIG_LOCATION=',sh)
        self.assertNotIn('"FEX ARM64"',sh)

    def test_only_one_immutable_AOT_artifact_set(self):
        sh=source("ports/sotc/android/run-sotc-bionic.sh")
        for marker in ("libSotcAot.so", "boot-native.bin", "aot-report.json",
                       '"$next/aot-report.json"', '"$next" "$base/user/aot"'):
            self.assertIn(marker,sh)
        self.assertIn('--prepared "$out" --report "$next/aot-report.json"',sh)
        sel=source("ports/sotc/android/aot/select_local_aot.py")
        for marker in ('"cmdline_sha256"', '"aot_boot_sha256"', '"patch_sha256"',
                       '"original_boot_sha256"', '"library_sha256"', '"tso"'):
            self.assertIn(marker,sel)

    def test_release_compiler_requires_zero_traps_and_no_tso(self):
        script=source("ports/sotc/android/aot/compile_local.py")
        self.assertIn('dirty!=0',script)
        self.assertIn('fatal unsupported instructions',script)
        self.assertIn('AOT_FLAGS = ("--resume-entries", "--no-callee-saved")',script)
        self.assertNotIn('AOT_FLAGS = ("--tso"',script)
        self.assertIn('AOT_COMPILER_VERSIONS = ("2",)',script)
        self.assertIn("embed_cmdline(patch_only,cmdline,native)",script)

    def test_sotc_installer_rejects_incomplete_AOT(self):
        java=source("android-launcher/app/src/main/java/ro/cobrabm/fexdroid/RuntimeInstaller.java")
        self.assertIn('"aot_mode',java)
        for required in ("libbbcpu.so","sotc-patched-compiler.sha256","cmdline_image.py",
                         "sotc_aot_select.py","helpers-aarch64.o"):
            self.assertIn(required,java)
        self.assertIn('preserveUserData(files, stage)',java)

    def test_release_packager_requires_native_backend_and_new_libcxx(self):
        script=source("ports/sotc/android/package_sotc_runtime.py")
        self.assertIn("strict_aot=os.environ.get('SOTC_REQUIRE_ON_DEVICE_AOT')=='1'",script)
        self.assertIn("if not source.is_file():",script)
        self.assertIn("shutil.copy2(source,libs/name)",script)
        self.assertIn("verify_libcxx_abi.py",script)
        self.assertIn("aot_mode='strict'",script)
        self.assertIn("'cmdline_image.py'",script)
        self.assertIn("on_device_aot_compiler_included=bool(compiler_archive)",script)
        self.assertIn("'libSotcAot.so').unlink(missing_ok=True)",script)

    def test_probe_early_vulkan_does_not_need_CPU_AOT(self):
        c=source("src/probe.c")
        first=c.find('guest_cpu_init(runtime_low_map);')
        early=c.find('return vulkan_smoke();', c.find('int main(int argc'))
        self.assertTrue(0 <= early < first)
        self.assertNotIn("getenv(\"SOTC_PORT\") && argc",c[:first])

    def test_packager_keeps_runtime_staging_directory_after_compiler_import(self):
        # Regression for 0.1.57 CI crash: importing "stage" directly in main()
        # overwrites the Path stage variable; packaging then fails at stage/'home'.
        script=source("ports/sotc/android/package_sotc_runtime.py")
        self.assertIn("from aot.stage_on_device_compiler import stage as stage_aot_compiler",script)
        self.assertIn("result=stage_aot_compiler(Path(compiler_archive),base)",script)
        self.assertNotIn("from aot.stage_on_device_compiler import stage\\n",script)

    def test_application_identity_for_install_over(self):
        app=source("android-launcher/app/build.gradle.kts")
        self.assertIn('applicationId = "com.sotc.android.daedalus"',app)
        self.assertIn('versionCode = 10069',app)
        self.assertIn('versionName = "0.1.69-aot-ux"',app)

if __name__=="__main__":
    unittest.main()
