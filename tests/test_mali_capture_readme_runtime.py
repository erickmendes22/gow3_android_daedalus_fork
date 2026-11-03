"""Execute the real capture branch with a POSIX shell, catching README command injection."""
from pathlib import Path
import os, shlex, subprocess, tempfile, unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools/android/bionic/run-bionic.sh"

class MaliCaptureReadme(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        src = SOURCE.read_text()
        i = src.index('if [ "$GOW3_MALI_AUTOCAPTURE" = 1 ] || [ "$GOW3_MALI_CPU_SNAPSHOTS" = 1 ]; then')
        i = src.rfind("\n", 0, i) + 1
        j = src.index("\n      fi", i) + len("\n      fi")
        cls.branch = src[i:j]

    def test_no_mksh_heredoc_tempfile(self):
        self.assertNotIn("<<'GOW3_CAPTURE_README'", self.branch)
        self.assertIn("} > \"$GOW3_MALI_CAPTURE_DIR/README.txt\"", self.branch)
        self.assertIn("printf '%s" + "\\n'", self.branch)
        self.assertNotIn("printf '%s" + "\\\\n'", self.branch)

    def test_full_script_parses(self):
        p = subprocess.run(["sh", "-n", str(SOURCE)], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)

    def evaluate(self, enabled, cpu_only=False):
        with tempfile.TemporaryDirectory() as folder:
            program = "set -eu\nbase=" + shlex.quote(folder) + "\n" + self.branch + "\n"
            env = {**os.environ, "GOW3_MALI_AUTOCAPTURE": str(int(enabled)),
                   "GOW3_MALI_CPU_SNAPSHOTS": str(int(cpu_only))}
            p = subprocess.run(["sh", "-c", program], capture_output=True, text=True, env=env)
            path = Path(folder) / "logs/mali-captures/README.txt"
            return p, path.read_text() if path.is_file() else None

    def test_enabled_writes_all_notes_without_running_prose(self):
        p, text = self.evaluate(True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stderr, "")
        self.assertIsNotNone(text)
        self.assertGreaterEqual(len(text.splitlines()), 10)
        for expected in ("PanVK stages:", "GOW3_MALI_VISUAL records",
                         "scene_????_3d_colorN.bmp", "scene_????_3d_depth.bmp",
                         "scene_????_3d_stencil.bmp", "scene_*_pass.txt",
                         "ahb_*.bmp", "frame_*.txt", "MALI_VIDEOOUT_SKIP"):
            self.assertIn(expected, text)

    def test_cpu_only_snapshots_create_readme_without_gpu_capture(self):
        p, text = self.evaluate(False, cpu_only=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIsNotNone(text)
        self.assertIn("ahb_*.bmp", text)

    def test_disabled_does_not_create_capture_directory(self):
        p, text = self.evaluate(False)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIsNone(text)

if __name__ == "__main__":
    unittest.main()
