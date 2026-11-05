"""A cached Python environment must survive a repository/checkout path change."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Tiny offline stand-ins for pip-installed build tools. The venv and its console
# script shebang are real, so moving the directory reproduces the Actions failure.
CREATE = '''import pathlib, subprocess, sys
root = pathlib.Path(sys.argv[-1])
subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(root)], check=True)
python = root / 'bin/python'
site = subprocess.check_output([str(python), '-c', 'import sysconfig; print(sysconfig.get_path("purelib"))'], text=True).strip()
pip = pathlib.Path(site) / 'pip'
pip.mkdir()
(pip / '__init__.py').write_text('')
(pip / '__main__.py').write_text(%r)
'''
INSTALL = '''import pathlib, sys, sysconfig
site = pathlib.Path(sysconfig.get_path("purelib"))
for name in ['mesonbuild', 'mako', 'yaml', 'packaging']:
    folder = site / name
    folder.mkdir(exist_ok=True)
    (folder / '__init__.py').write_text('')
(site / 'mesonbuild/mesonmain.py').write_text('')
meson = pathlib.Path(sys.executable).parent / 'meson'
meson.write_text('#!' + sys.executable + '\\nprint("fixture meson")\\n')
meson.chmod(0o755)
'''


class MesaVenvTests(unittest.TestCase):
    def test_moved_cache_is_recreated_and_healthy_cache_is_reused(self):
        if not shutil.which('bash'):
            self.skipTest('bash unavailable')
        source = (ROOT / 'tools/android/build/build_turnip.sh').read_text()
        block = source.split('venv=$deps/mesa-venv', 1)[1].split('export PATH="$venv/bin:$PATH"', 1)[0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            helper = root / 'create.py'
            helper.write_text(CREATE % INSTALL)
            deps = root / 'deps'
            old = deps / 'old-checkout'
            subprocess.run([sys.executable, str(helper), str(old)], check=True, capture_output=True)
            subprocess.run([str(old / 'bin/python'), '-m', 'pip', 'install'], check=True, capture_output=True)
            cached = deps / 'mesa-venv'
            old.rename(cached)
            meson = cached / 'bin/meson'
            self.assertTrue(os.access(meson, os.X_OK))
            self.assertIn(str(old), meson.read_text())
            # This executable bit passed the old build check, but the shebang target is gone.
            self.assertFalse(old.exists())
            hostbin = root / 'hostbin'
            hostbin.mkdir()
            hostpython = hostbin / 'python3'
            hostpython.write_text('#!/bin/sh\nexec ' + shutil.which('python3') + ' ' + str(helper) + ' "$@"\n')
            hostpython.chmod(0o755)
            env = dict(os.environ, PATH=str(hostbin) + os.pathsep + os.environ['PATH'])
            script = 'set -euo pipefail\ndeps="$1"\nvenv="$deps/mesa-venv"\ndie() { exit 1; }\n' + block
            first = subprocess.run(['bash', '-c', script, 'test', str(deps)], env=env,
                                   capture_output=True, text=True, timeout=30)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            self.assertIn('Recreating', first.stdout)
            self.assertNotIn(str(old), meson.read_text())
            self.assertEqual(subprocess.check_output([str(meson), '--version'], text=True).strip(), 'fixture meson')
            marker = cached / 'keep-cache'
            marker.write_text('retained')
            second = subprocess.run(['bash', '-c', script, 'test', str(deps)], env=env,
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertNotIn('Recreating', second.stdout)
            self.assertTrue(marker.is_file())
