"""Reject invalid experimental runtime payloads before distributing a test APK."""
from paths import ROOT
import hashlib
import importlib.util
import io
import tarfile
import unittest

spec=importlib.util.spec_from_file_location('bionic_apk',ROOT/'tools/android/bionic/validate_apk.py')
validator=importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)

class BionicPackageValidation(unittest.TestCase):
    def payload(self,name):
        data=io.BytesIO()
        with tarfile.open(fileobj=data,mode='w:gz') as archive:
            item=tarfile.TarInfo(name);item.size=1
            archive.addfile(item,io.BytesIO(b'x'))
        return data.getvalue()

    def test_rejects_modified_runtime(self):
        with self.assertRaisesRegex(ValueError,'hash mismatch'):
            validator.validate_payload(b'changed','0'*64)

    def test_rejects_game_content_old_rootfs_and_unsafe_paths(self):
        for name in ['rootfs/bin/sh','gow3port/game/eboot.bin','game.pkg','../escape']:
            with self.subTest(name=name):
                payload=self.payload(name)
                with self.assertRaises(ValueError):
                    validator.validate_payload(payload,hashlib.sha256(payload).hexdigest())

    def test_rejects_incomplete_archive_even_with_matching_hash(self):
        payload=self.payload('runtime-manifest.json')
        with self.assertRaisesRegex(ValueError,'Missing Bionic runtime file'):
            validator.validate_payload(payload,hashlib.sha256(payload).hexdigest())

    def test_rejects_removed_frame_generation_components(self):
        for name in ['gow3port/arm64/lib/liblsfg-gow3.so',
                     'gow3port/arm64/lsfg/liblsfg-vk.so']:
            with self.subTest(name=name):
                payload=self.payload(name)
                with self.assertRaisesRegex(ValueError,'Removed frame-generation component'):
                    validator.validate_payload(payload,hashlib.sha256(payload).hexdigest())

    def test_licenses_for_pinned_mit_bloodframe_do_not_trigger_legacy_layer_rejection(self):
        # This is the exact filename that broke the signed Bionic APK validator
        # even though there was no old LSFG Vulkan layer in the payload.
        path = 'gow3port/licenses/bloodframe-lsfg-vk.LICENSE.md'
        payload = self.payload(path)
        with self.assertRaisesRegex(ValueError, 'Missing Bionic runtime file'):
            validator.validate_payload(payload, hashlib.sha256(payload).hexdigest())

    def test_bloodframe_license_exception_is_restricted_to_notices_directory(self):
        for path in [
            'gow3port/arm64/lib/bloodframe-lsfg-vk.LICENSE.md',
            'gow3port/arm64/lsfg/bloodframe-lsfg-vk.LICENSE.md',
            'gow3port/licenses/lsfg-vk.so',
        ]:
            with self.subTest(path=path):
                payload=self.payload(path)
                with self.assertRaisesRegex(ValueError, 'Removed frame-generation component'):
                    validator.validate_payload(payload, hashlib.sha256(payload).hexdigest())

    def test_proprietary_lossless_dll_remains_forbidden(self):
        payload = self.payload('gow3port/Lossless.dll')
        with self.assertRaisesRegex(ValueError, 'Unexpected game/glibc content'):
            validator.validate_payload(payload, hashlib.sha256(payload).hexdigest())
