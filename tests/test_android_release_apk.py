import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.android.validate_release_apk import ApkError, validate_apk
from tests.test_android_runtime_archive import write_fixture


class ReleaseApkTests(unittest.TestCase):
    def _apk(self, directory, digest_override=None):
        runtime = Path(directory) / 'runtime.tar.gz'
        write_fixture(runtime)
        payload = runtime.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if digest_override is not None:
            digest = digest_override
        apk = Path(directory) / 'GamePort.apk'
        with zipfile.ZipFile(apk, 'w') as package:
            package.writestr('assets/runtime.payload', payload)
            package.writestr('assets/runtime.sha256', digest + '\n')
            package.writestr('lib/arm64-v8a/libfxdisplay.so', b'bridge')
            package.writestr('lib/arm64-v8a/libfxio.so', b'bridge')
            package.writestr('classes.dex', b'ro/cobrabm/fexdroid')
        return apk, digest

    def test_signed_apk_fixture_passes_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            apk, digest = self._apk(directory)
            result = validate_apk(apk)
            self.assertEqual(result['payload_sha256'], digest)

    def test_bad_payload_digest_has_checksum_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            apk, _ = self._apk(directory, '0' * 64)
            with self.assertRaisesRegex(ApkError, 'checksum'):
                validate_apk(apk)

    def test_nested_rootfs_has_layout_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / 'runtime.tar.gz'
            write_fixture(runtime, 'gow3port/rootfs/tmp')
            payload = runtime.read_bytes()
            digest = hashlib.sha256(payload).hexdigest()
            apk = Path(directory) / 'GamePort.apk'
            with zipfile.ZipFile(apk, 'w') as package:
                package.writestr('assets/runtime.payload', payload)
                package.writestr('assets/runtime.sha256', digest + '\n')
                package.writestr('lib/arm64-v8a/libfxdisplay.so', b'bridge')
                package.writestr('lib/arm64-v8a/libfxio.so', b'bridge')
                package.writestr('classes.dex', b'ro/cobrabm/fexdroid')
            with self.assertRaisesRegex(ApkError, 'archive completeness'):
                validate_apk(apk)
