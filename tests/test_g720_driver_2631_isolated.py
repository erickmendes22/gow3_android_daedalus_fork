"""Mali G720/G615 automatic PanVK V3 parity, with 26.3.1 remaining explicit."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
JAVA = (ROOT / "android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GpuDriverManager.java").read_text()
LAUNCH = (ROOT / "tools/android/bionic/run-bionic.sh").read_text()


class G720DriverParityTests(unittest.TestCase):
    def test_mali_auto_defaults_to_bachata_v3(self):
        self.assertIn('if (maliCandidate()) return context.getString(R.string.gpu_driver_panvk);', JAVA)
        self.assertIn('final boolean wantNext = "panvk-next".equals(selection);', JAVA)
        self.assertNotIn('nextPanvkVerifiedAutoDevice', JAVA)
        self.assertIn('return name.contains("g720") || name.contains("g615");', JAVA)
        self.assertIn('MALI_DEFAULT_MIGRATION_KEY', JAVA)
        self.assertIn('migratedMaliSelection(old,true,false)', JAVA)
        self.assertIn('if (!old.equals(migrated)) editor.putString("gpu_driver",migrated)', JAVA)
        self.assertIn('"com.gow3.android.bionic".equals(pkg)', JAVA)
        self.assertIn('"com.gow3.android.bionic.malitest".equals(pkg)', JAVA)

    def test_explicit_other_driver_and_user_selection_preserved(self):
        self.assertIn('PANVK_NEXT_SHA256="0c61ef0cdd5c9314715c4a0cc34a5929dbd727ce7a30545b947577e83600b900"', JAVA)
        self.assertIn('PANVK_SHA256="68d4eccc1442cb0bef08228c90127388e68bf6087898abc492c717b9a06ca61f"', JAVA)
        self.assertIn('if ("panvk".equals(selection) || "panvk-next".equals(selection)', JAVA)
        self.assertIn('drv = bundledPanvk(context, wantNext);', JAVA)
        self.assertIn('PANVK_KBASE_GPU_SEMAPHORE_WAITS=', LAUNCH)
        self.assertIn('PANVK_KBASE_SKIP_HEAP_OPS=', LAUNCH)
        self.assertIn('PANVK_ZS_PRELOAD_ALWAYS=', LAUNCH)

    def test_identifiable_active_driver(self):
        self.assertIn('GOW3_GPU_AUTO_REASON', JAVA)
        self.assertIn('PanVK 26.3.1 (explicit alternative)', JAVA)
        self.assertIn('PanVK 3.2 (Bachata V3 Mali parity)', JAVA)


if __name__ == "__main__":
    unittest.main()
