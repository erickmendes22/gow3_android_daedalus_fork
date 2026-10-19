"""CUSA01715 01.02 resolution operand verification and Android FSR presets.

Small synthetic instruction samples are from the user's exact PS4 SELF, SHA-256
6e72330e9092e5164049b865e5568f2d450904001a73fe0a2f4b39194c195b3c.
Only byte sequences required for signature validation are retained; never bundle
or copy the game executable into the APK or test artifacts.
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import patches
import launch_env

XML = ROOT / "patches/God_of_War_III_Remastered.xml"
HASH = patches.CUSA01715_0102_ANDROID_SHA


def sample_image():
    # Exact original bytes at ALL nine unique signature sites in this eboot,
    # including the independent Video Arena write.
    fragments = [
        (0x005f0c4c, "48 8d 75 a0 89 c7 e8 b9 9d 0f 00 41 c7 45 0c 80 07 00 00"
                     " 41 c7 45 10 38 04 00 00 66 41 c7 45 14 80 07"
                     " 66 41 c7 45 16 38 04"),
        (0x005643e0, "c7 04 24 38 04 00 00 48 8d 3d 42 e6 28 00"
                     " 41 b9 80 07 00 00 4c 89 f9 4d 89 e0 e8 21 01 00 00"),
        (0x005ff883, "bf 00 01 00 00 b9 80 07 00 00 41 b8 38 04 00 00"),
        (0x005b7394, "83 bb 80 01 00 00 00 74 32 4c 8d 7d a8"),
        (0x007cd910, "00 00 00 43 00 00 80 3f 00 00 00 50 00 00 00 00 00 04 00 00"),
        # Upstream's half-resolution post-process table, original 960x540.
        (0x007f2a34, "00 00 00 00 0a e0 f2 00 c0 03 00 00 1c 02 00 00 01 00 00 00"
                      " 00 00 00 00"),
    ]
    image = bytearray(0x007f2a54 - patches.EBOOT_BASE)
    for addr, raw in fragments:
        data = bytes.fromhex(raw)
        offset = addr - patches.EBOOT_BASE
        image[offset:offset + len(data)] = data
    return image


class Cusa01715ResolutionTests(unittest.TestCase):
    def test_900p_writes_all_eight_verified_geometry_operands(self):
        image = sample_image()
        for expand in (True, False):
            writes = patches.compile_patches(
                XML, ['Resolution Patch - 900p'], '01.02', [(0, len(image))], image,
                expand_video_arena=expand)
            self.assertEqual(len(writes), 11 if expand else 10)
            # Ignore the two new postprocessing writes and the optional video-arena write:
            # the eight geometry operands must still match their independently verified sites.
            geometry = [(offset, data) for offset, data in writes
                        if offset + patches.EBOOT_BASE in patches.CUSA01715_0102_SITES]
            self.assertEqual(len(geometry), 8)
            for i, (offset, data) in enumerate(geometry):
                self.assertEqual(offset + patches.EBOOT_BASE, patches.CUSA01715_0102_SITES[i])
                expected = 1600 if patches.CUSA01715_0102_FIELDS[i] == 'width' else 900
                self.assertEqual(data, expected.to_bytes(len(data), 'little'))

    def test_signatures_are_unique_and_identify_exact_operands(self):
        image = sample_image()
        segs = [(0, len(image))]
        for preset in ["1280x720", "960x540", "854x480", "752x424", "640x360", "426x240"]:
            with self.subTest(preset=preset):
                writes, evidence = patches.android_native_resolution_writes(
                    XML, image, segs, HASH, preset, ["Resolution Patch - 720p"])
                self.assertEqual(len(writes), 8)
                self.assertEqual(evidence["render"], preset)
                self.assertEqual(evidence["output"], preset)
                self.assertEqual(tuple(int(x, 16) for x in evidence["verified_sites"]),
                                 patches.CUSA01715_0102_SITES)
                for i, site in enumerate(patches.CUSA01715_0102_SITES):
                    payload = writes[site - patches.EBOOT_BASE]
                    width, height = map(int, preset.split("x"))
                    target = width if patches.CUSA01715_0102_FIELDS[i] == "width" else height
                    self.assertEqual(payload, target.to_bytes(len(payload), 'little'))

    def test_shadow_branch_patch_is_validated_by_cusa_signature(self):
        image = sample_image()
        writes = patches.compile_patches(
            XML, ["Disable Dynamic Shadows"], "01.02",
            [(0, len(image))], image)
        self.assertEqual(writes, [(0x005b739b - patches.EBOOT_BASE, b"\xeb\x32")])
        # The source ELF uses je +0x32, not an unconditional branch.
        self.assertEqual(
            image[0x005b739b - patches.EBOOT_BASE:
                  0x005b739d - patches.EBOOT_BASE], b"\x74\x32")

    def test_mismatched_original_byte_rejects_entire_patch(self):
        image = sample_image()
        image[0x005f0c5b - patches.EBOOT_BASE] ^= 0x80
        with self.assertRaises(ValueError):
            patches.android_native_resolution_writes(
                XML, image, [(0, len(image))], HASH, "640x360",
                ["Resolution Patch - 720p"])

    def test_wrong_eboot_sha_or_missing_720p_patch_rejected(self):
        image = sample_image()
        for sha, names in [("0"*64, ["Resolution Patch - 720p"]), (HASH, [])]:
            with self.subTest(sha=sha, names=names), self.assertRaises(ValueError):
                patches.android_native_resolution_writes(
                    XML, image, [(0, len(image))], sha, "640x360", names)

    def test_one_canonical_selection_for_each_resolution_without_fsr(self):
        verified = {"title_id": "CUSA01715", "app_version": "01.02",
                    "eboot_sha256": HASH, "eboot_matches": True,
                    "reason": "validated"}
        direct = {"240p": "426x240", "360p": "640x360",
                  "424p": "752x424", "540p": "960x540"}
        for resolution, actual in direct.items():
            with self.subTest(resolution=resolution), tempfile.TemporaryDirectory() as t:
                folder = Path(t)
                config = folder / "gow3.ini"
                config.write_text(f"upscaler=fsr3\nrender_resolution={resolution}\n")
                with patch.object(patches, "patch_profile_status", return_value=verified):
                    plan = launch_env.derive(folder, config, folder / "state.json",
                                             {"GOW3_ANDROID_PORT": "1"})
                self.assertEqual(plan["updates"]["GOW3_PATCH_INPUT_RES"], actual)
                self.assertEqual(plan["updates"]["GOW3_UPSCALER"], "none")
                self.assertNotIn("GOW3_RENDER_RES", plan["updates"])
                self.assertIn("Resolution Patch - 720p", plan["patch_names"])

        # 480p and 720p already have PS4 resolution patches. There must NOT
        # be another 854x480 or 1280x720 entry for the same game size.
        for resolution in ("480p", "720p"):
            with self.subTest(resolution=resolution), tempfile.TemporaryDirectory() as t:
                folder = Path(t)
                config = folder / "gow3.ini"
                config.write_text(f"render_resolution={resolution}\n")
                with patch.object(patches, "patch_profile_status", return_value=verified):
                    plan = launch_env.derive(folder, config, folder / "state.json",
                                             {"GOW3_ANDROID_PORT": "1"})
                self.assertNotIn("GOW3_PATCH_INPUT_RES", plan["updates"])
                self.assertIn(f"Resolution Patch - {resolution}", plan["patch_names"])

    def test_old_pixel_resolutions_are_migrated_without_duplicate_entries(self):
        from graphics_options import canonical_resolution, RESOLUTIONS, patch_names, startup_options
        aliases = {"1280x720": "720p", "854x480": "480p",
                   "960x540": "540p", "752x424": "424p",
                   "640x360": "360p", "426x240": "240p"}
        for old, canonical in aliases.items():
            with self.subTest(old=old):
                self.assertEqual(canonical_resolution(old), canonical)
                self.assertEqual(startup_options({"render_resolution": old})["render_resolution"], canonical)
        self.assertEqual(len(RESOLUTIONS), len(set(RESOLUTIONS)))
        verified = {"title_id": "CUSA01715", "app_version": "01.02",
                    "eboot_sha256": HASH, "eboot_matches": True, "reason": "validated"}
        for old, canonical in aliases.items():
            with self.subTest(legacy_config=old), tempfile.TemporaryDirectory() as t:
                folder = Path(t)
                config = folder / "gow3.ini"
                config.write_text(f"render_resolution={old}\n")
                with patch.object(patches, "patch_profile_status", return_value=verified):
                    plan = launch_env.derive(folder, config, folder / "state.json",
                                             {"GOW3_ANDROID_PORT": "1"})
                self.assertIn(f"render_resolution={canonical}\n", config.read_text())
                if canonical in ("480p", "720p"):
                    self.assertNotIn("GOW3_PATCH_INPUT_RES", plan["updates"])
                    self.assertIn(f"Resolution Patch - {canonical}", plan["patch_names"])
                else:
                    self.assertIn("GOW3_PATCH_INPUT_RES", plan["updates"])



if __name__ == "__main__":
    unittest.main()
