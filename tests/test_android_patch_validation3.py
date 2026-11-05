"""A rejected line must never leave an earlier part of the patch active."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from patches import compile_patches


class PatchValidationTests(unittest.TestCase):
    def compile(self, lines, *, image=b'ABCD', names=None):
        with tempfile.TemporaryDirectory() as folder:
            xml = Path(folder) / 'fixture.xml'
            xml.write_text('<Patch><Metadata Name="test" AppVer="01.02"><PatchList>' +
                           lines + '</PatchList></Metadata></Patch>')
            skipped = {}
            writes = compile_patches(xml, names or ['test'], '01.02', [(0, 4)], image, skipped)
            return writes, skipped

    def test_later_invalid_write_rejects_entire_patch(self):
        writes, skipped = self.compile(
            '<Line Type="bytes" Address="0x400000" Pattern="41 42" Value="9090"/>'
            '<Line Type="bytes" Address="0x400003" Pattern="43 44" At="1" Value="9090"/>')
        self.assertEqual(writes, [])
        self.assertIn('test', skipped)

    def test_real_image_requires_signature(self):
        writes, skipped = self.compile('<Line Type="bytes" Address="0x400000" Value="90"/>')
        self.assertEqual(writes, [])
        self.assertIn('missing signature', skipped['test'])

    def test_valid_signature_and_missing_patch_are_independent(self):
        writes, skipped = self.compile(
            '<Line Type="bytes" Address="0x400000" Pattern="41 42" Value="9090"/>',
            names=['test', 'missing'])
        self.assertEqual(writes, [(0, b'\x90\x90')])
        self.assertIn('missing', skipped)
