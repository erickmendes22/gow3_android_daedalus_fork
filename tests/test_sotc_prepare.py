# SPDX-License-Identifier: GPL-2.0-or-later
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
PATH=Path(__file__).resolve().parents[1]/'ports/sotc/android/prepare_game.py'
spec=importlib.util.spec_from_file_location('sotc_prepare',PATH)
sp=importlib.util.module_from_spec(spec)
spec.loader.exec_module(sp)
def make_sfo(title):
    key=b'TITLE_ID\x00'
    value=title.encode()+b'\x00'
    return b'\x00PSF'+struct.pack('<IIII',0x101,36,36+len(key),1)+struct.pack('<HHIII',0,0x204,len(value),len(value),0)+key+value

class TestSotcPrepare(unittest.TestCase):
    def test_sfo(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'param.sfo'
            for tid in sp.SUPPORTED:
                p.write_bytes(make_sfo(tid))
                self.assertEqual(sp.sfo_title_id(p),tid)
            p.write_bytes(b'invalid')
            with self.assertRaises(ValueError):
                sp.sfo_title_id(p)
    def test_cannot_write_dump(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with self.assertRaises(ValueError):
                sp.prepare(root,root/'game',root/'game/out')
    def test_prepare_and_cache(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            upstream=root/'upstream'
            folder=upstream/'scripts'
            folder.mkdir(parents=True)
            outputs=['boot.bin','boot-linked.bin','content.bin','sotc-cpu.bin','patches.bin']
            for script,name in zip(sp.SCRIPTS,outputs):
                (folder/script).write_text('from pathlib import Path\nimport sys\nPath(sys.argv[sys.argv.index("--out")+1],"'+name+'").write_bytes(b"test")\n')
            game=root/'dump'
            (game/'sce_sys').mkdir(parents=True)
            (game/'eboot.bin').write_bytes(b'O\x15=\x1d' + b'\x00'*32)
            (game/'sce_sys/param.sfo').write_bytes(make_sfo('CUSA08809'))
            out=root/'out'
            self.assertFalse(sp.prepare(upstream,game,out)['cached'])
            self.assertTrue(sp.prepare(upstream,game,out)['cached'])
            self.assertTrue(all((out/n).is_file() for n in sp.OUTPUTS))
            (game/'sce_sys/param.sfo').write_bytes(make_sfo('UNSUPPORTED'))
            with self.assertRaises(ValueError):
                sp.prepare(upstream,game,out)
if __name__=='__main__':
    unittest.main()
