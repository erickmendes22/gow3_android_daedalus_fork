import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANDROID = ROOT / 'tools/android'


class AndroidBuildInputTests(unittest.TestCase):
    def test_critical_android_scripts_keep_executable_git_modes(self):
        """Reject 100644 regressions before compiling FEX, Turnip and LSFG.

        tar.add() preserves the tracked source mode for run-gow3.sh.
        The last APK CI compiled every native component, then failed because
        the launch script had silently changed from 100755 to 100644.
        """
        paths = (
            "tools/android/device/run-gow3.sh",
            "tools/android/build/build_arm64.sh",
            "tools/android/build/build_turnip.sh",
            "tools/android/build/build_lsfg.sh",
            "tools/android/apk/build_release_apk.sh",
            "android-launcher/gradlew",
        )
        for relative in paths:
            with self.subTest(path=relative):
                file = ROOT / relative
                self.assertTrue(file.is_file(), relative)
                self.assertTrue(file.stat().st_mode & 0o111,
                                f"{relative} is not executable on disk")
                status = subprocess.check_output(
                    ["git", "ls-files", "--stage", "--", relative],
                    cwd=ROOT, text=True).strip()
                self.assertTrue(status.startswith("100755 "),
                                f"{relative} must be tracked as git mode 100755, got {status!r}")

    def test_bridge_provenance_matches_allow_list(self):
        provenance = json.loads((ANDROID / 'bridges/provenance.json').read_text())
        self.assertEqual(provenance['abi'], 'arm64-v8a')
        self.assertEqual(provenance['source_revision'],
                         '2b03ec73c3507b640fba1942fb8d99b43b88945a')
        self.assertEqual({entry['archive_path'] for entry in provenance['files']}, {
            'lib/arm64-v8a/libfxdisplay.so', 'lib/arm64-v8a/libfxio.so'})
        for entry in provenance['files']:
            path = ROOT / entry['output_path']
            self.assertTrue(path.is_file(), path)
            self.assertEqual(path.stat().st_size, entry['size'])

    def test_debug_manifest_reuses_local_graphics_artifacts(self):
        manifest = json.loads((ANDROID / 'debug/runtime-manifest.json').read_text())
        self.assertEqual(manifest['profile'], 'debug')
        self.assertIn('rootfs/usr/share/vulkan/icd.d/freedreno_icd.aarch64.json',
                      manifest['turnip_variants'])
        self.assertIn('rootfs/usr/share/vulkan/icd.d/freedreno_gen8_icd.aarch64.json',
                      manifest['turnip_variants'])
        self.assertFalse(any('lsfg' in entry['path'] for entry in manifest['required_paths']))

    def test_scripted_patch_inputs_exist_and_are_game_free(self):
        paths = [
            ANDROID / 'mesa-patches/README.md',
            ANDROID / 'mesa-patches/gen8',
            ANDROID / 'lsfg-patches',
        ]
        for path in paths:
            self.assertTrue(path.exists(), path)
        patch_files = list((ANDROID / 'mesa-patches').rglob('*.patch'))
        patch_files += list((ANDROID / 'lsfg-patches').glob('*.patch'))
        self.assertGreater(len(patch_files), 0)
        forbidden = ('eboot.bin', 'sce_sys', 'sce_module', 'Lossless.dll')
        for path in patch_files:
            text = path.read_text(errors='replace')
            self.assertFalse(any(word in text for word in forbidden), path)

    def test_runtime_manifest_keeps_generated_driver_contract(self):
        manifest = json.loads((ANDROID / 'runtime/runtime-manifest.json').read_text())
        self.assertIn('rootfs/usr/share/vulkan/icd.d/freedreno_icd.aarch64.json',
                      manifest['turnip_variants'])
        self.assertIn('rootfs/usr/share/vulkan/icd.d/freedreno_gen8_icd.aarch64.json',
                      manifest['turnip_variants'])
        self.assertEqual(manifest['port_arch_root'], 'gow3port/arm64')

    def test_release_assembler_reports_all_missing_generated_inputs(self):
        result = subprocess.run(
            ['python3', 'tools/android/build_release_runtime.py'],
            cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        output = result.stdout + result.stderr
        self.assertIn('Missing Android runtime inputs:', output)
        self.assertIn('Gen8 Turnip:', output)
        self.assertNotIn('LSFG:', output)

    def test_player_lossless_dll_stays_out_of_every_build_product(self):
        """The launcher never ships Lossless.dll; players import their own (Home page)."""
        assembler = (ANDROID / 'runtime/build_release_runtime.py').read_text()
        self.assertIn('Lossless.dll', assembler)
        banned = assembler.split('banned', 1)[1]
        self.assertIn('Lossless.dll', banned, 'Lossless.dll must stay in the payload ban list')

        this_file = Path(__file__).read_text()
        self.assertIn("'Lossless.dll'", this_file, 'Lossless.dll must stay in the patch-input ban list')
