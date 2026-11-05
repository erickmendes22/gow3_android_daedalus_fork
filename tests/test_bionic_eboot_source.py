"""Source contract: GoW3 base boot never requires a selected update.
The native parity test exercises the actual SELF/ELF parser on a synthetic base.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class BaseEbootSourceTests(unittest.TestCase):
    def test_optional_update_and_live_launch_selection(self):
        shell=(ROOT/"tools/android/bionic/run-bionic.sh").read_text()
        activity=(ROOT/"android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java").read_text()
        self.assertIn('update=${GOW3_PATCH_DIR:-none} (update optional)',shell)
        self.assertIn('if [ -n "${GOW3_PATCH_DIR:-}" ]; then',shell)
        self.assertIn('gameDir=gamePrefs.getString("game_dir",null);',activity)
        self.assertIn('updateDir=gamePrefs.getString("update_dir",null);',activity)

    def test_bionic_eboot_mmap_parity_and_diagnostic(self):
        io=(ROOT/"tools/android/bionic/prepare/io.cpp").read_text()
        native=(ROOT/"tools/android/bionic/prepare/gow3_prepare.cpp").read_text()
        self.assertIn('mmap header disagrees with pread',io)
        self.assertIn('pread(fd, disk_header, sizeof(disk_header), 0)',io)
        self.assertIn('inconsistent = std::memcmp(m, disk_header, compare_size) != 0;',io)
        for token in ('source_path', 'first16=%s', 'type=%s','sha256_hex(bytes)','s = parse_self(bytes)'):
            self.assertIn(token,native)
        self.assertLess(native.index('sha256_hex(bytes)'),native.index('s = parse_self(bytes)'))

if __name__ == "__main__":
    unittest.main()
