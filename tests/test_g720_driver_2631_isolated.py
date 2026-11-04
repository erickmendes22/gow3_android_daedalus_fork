"""CSF v12 26.3.1 default + one-time upgrade of legacy G720 installations."""
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]
JAVA=(ROOT/"android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GpuDriverManager.java").read_text()
LAUNCH=(ROOT/"tools/android/bionic/run-bionic.sh").read_text()

class G720DriverABTests(unittest.TestCase):
 def test_isolated_auto_branch(self):
  self.assertIn('nextPanvkVerifiedAutoDevice(Context context)',JAVA)
  self.assertIn('return normalized.contains("g720") || normalized.contains("g615");',JAVA)
  self.assertIn('return name.contains("g720") || name.contains("g615");',JAVA)
  self.assertIn('MALI_DEFAULT_MIGRATION_KEY',JAVA)
  self.assertIn('migratedMaliSelection(old,true,false)',JAVA)
  self.assertIn('if (!old.equals(migrated)) editor.putString("gpu_driver",migrated)',JAVA)
  self.assertIn('.putString(MALI_DEFAULT_MIGRATION_KEY,"1").commit()',JAVA)
  self.assertIn('normalized.contains("g720")',JAVA)
  self.assertIn('isCompatibleMaliAutoUpgrade()',JAVA)
  self.assertIn('"com.gow3.android.bionic".equals(pkg)',JAVA)
  self.assertIn('"com.gow3.android.bionic.malitest".equals(pkg)',JAVA)
 def test_both_drivers_keep_explicit_control(self):
  self.assertIn('PANVK_NEXT_SHA256="0c61ef0cdd5c9314715c4a0cc34a5929dbd727ce7a30545b947577e83600b900"',JAVA)
  self.assertIn('PANVK_SHA256="68d4eccc1442cb0bef08228c90127388e68bf6087898abc492c717b9a06ca61f"',JAVA)
  self.assertIn('if ("panvk".equals(selection) || "panvk-next".equals(selection)',JAVA)
  self.assertIn('drv = bundledPanvk(context, false);',JAVA)
  self.assertIn('if (!"auto".equals(selection) || !wantNext)',JAVA)
  self.assertIn('GOW3_MALI_IMAGE_RAR_ELIDE=${GOW3_MALI_IMAGE_RAR_ELIDE:-0}',LAUNCH)
 def test_driver_log_identity(self):
  self.assertIn('GOW3_GPU_AUTO_REASON',JAVA)
  self.assertIn('PanVK 26.3.1 (default Mali G720/G615)',JAVA)
  self.assertIn('PanVK 3.2 (legacy compatibility)',JAVA)
if __name__=="__main__": unittest.main()
