"""Byte parity of native preparation with the existing GoW3 Python pipeline."""
from paths import ROOT
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from bionic_prepare_fixture import synthetic_game, write_game
from prepare import parse_self


class BionicPrepareParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.native = ROOT/'out/host/gow3-prepare'
        if not cls.native.is_file():
            raise unittest.SkipTest('Build the host tool with tools/android/bionic/build_prepare.sh host')

    def compare(self, path, root):
        py = root/'py'
        native = root/'native'
        env = dict(os.environ, PYTHONPATH=str(ROOT/"scripts"))
        a = subprocess.run([sys.executable, str(ROOT/'tools/android/inputs/prepare_game.py'), str(path), str(py)],
                           env=env, text=True, capture_output=True)
        b = subprocess.run([str(self.native), str(path), str(native)], env=env, text=True, capture_output=True)
        self.assertEqual(b.returncode, a.returncode, f'Python: {a.stderr}\nNative: {b.stderr}')
        if a.returncode == 0:
            self.assertIn("Game image:", b.stdout)
        if a.returncode == 0:
            for name in ['boot-linked.bin','content.bin','game-source.json']:
                self.assertEqual((native/name).read_bytes(), (py/name).read_bytes(), name)
            self.assertEqual((native/'eboot.elf').read_bytes(), bytes(parse_self((path/'eboot.bin').read_bytes())[0]))
        return a, b

    def test_synthetic_game_imports_relocations_tls_and_marker_reuse(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            game = write_game(root/'game', *synthetic_game())
            a, _ = self.compare(game, root)
            self.assertEqual(a.returncode, 0, a.stderr)
            self.compare(game, root)
            # Patch compilation needs the decoded ELF even when the base image cache matches.
            (root/'native/eboot.elf').unlink()
            self.compare(game, root)

    def test_user_content_parameters(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            game = write_game(root/'game', *synthetic_game(), params={
                'USER_DEFINED_PARAM_1': 0, 'USER_DEFINED_PARAM_2': 100,
                'USER_DEFINED_PARAM_3': 0xffffffff, 'USER_DEFINED_PARAM_4': 42})
            a, _ = self.compare(game, root)
            self.assertEqual(a.returncode, 0, a.stderr)

    def test_damaged_image_and_missing_module_fail(self):
        for missing in ['eboot.bin','sce_module/libc.prx','sce_module/libSceFios2.prx']:
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                game = write_game(root/'game', *synthetic_game())
                (game/missing).unlink()
                a, _ = self.compare(game, root)
                self.assertNotEqual(a.returncode, 0)
                self.assertFalse((root/'native/game-source.json').exists())

    def test_unrecognized_base_eboot_reports_actual_file_and_keeps_update_optional(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            game = write_game(root/'game', *synthetic_game())
            invalid = b"NOT_A_SELF_OR_ELF" + bytes(range(32))
            (game/'eboot.bin').write_bytes(invalid)
            a, b = self.compare(game, root)
            self.assertNotEqual(a.returncode, 0)
            self.assertIn("Game executable:", b.stdout)
            self.assertIn("first16=4e4f545f415f53454c465f4f525f454c", b.stdout)
            self.assertIn("type=UNRECOGNIZED", b.stdout)
            self.assertIn("sha256=", b.stdout)
            self.assertIn("expected PS4 SELF or ELF", b.stderr)
            self.assertNotIn("update is required", b.stderr)
            self.assertFalse((root/'native/boot-linked.bin').exists())

    def test_empty_sfo_fails_without_cached_image(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            game = write_game(root/'game', *synthetic_game())
            (game/'sce_sys/param.sfo').write_bytes(b'')
            a, _ = self.compare(game, root)
            self.assertNotEqual(a.returncode, 0)
            self.assertFalse((root/'native/game-source.json').exists())


if __name__ == '__main__':
    unittest.main()
