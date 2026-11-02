#!/usr/bin/env python3
"""Android GUI->Bionic environment and safe guest GPU writeback integration."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
UI=(ROOT/"android-launcher/app/src/main/java/com/gow3/android/ui/SotcScreen.kt").read_text()
JAVA=(ROOT/"android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java").read_text()
RUN=(ROOT/"ports/sotc/android/run-sotc-bionic.sh").read_text()
PACKAGE=(ROOT/"ports/sotc/android/package_sotc_runtime.py").read_text()
NATIVE=(ROOT/"src/runtime_memory.c").read_text()

class GuardedWritebackMode(unittest.TestCase):
    def test_opt_in_only_with_unchanged_readback_selector(self):
        self.assertIn('values["sotc_write_fast"]?:"0"',UI)
        self.assertIn('save("sotc_write_fast",if(it)"1" else "0")',UI)
        self.assertIn('values["sotc_readbacks"]?:"2"',UI)
        self.assertIn('env.put("SOTC_WRITE_FAST",',JAVA)
        self.assertIn('"1".equals(setting("sotc_write_fast")) ? "1" : "0"',JAVA)
        self.assertIn('env.put("BB_READBACKS",rbMode);',JAVA)
        self.assertIn("export SOTC_WRITE_FAST="+chr(36)+"{SOTC_WRITE_FAST:-0}",RUN)
        self.assertIn('case "$SOTC_WRITE_FAST" in',RUN)
        self.assertIn('sotc_write_fast=0',PACKAGE)
        self.assertIn('sotc_vm_range_cache=1',PACKAGE)
        self.assertIn('sotc_readbacks=2',PACKAGE)
    def test_original_guest_writeback_still_available(self):
        self.assertIn('if (sotc_write_backing_fast(address,data,size)) return 1;',NATIVE)
        self.assertIn('if (!sotc_wb_copy_enter()) return 0;',NATIVE)
        self.assertIn('sotc_wb_writer_begin();',NATIVE)
        self.assertIn('sotc_wb_writer_end();',NATIVE)
        self.assertIn('read_lock();',NATIVE)
        self.assertIn('size>(256u<<10)',NATIVE)

if __name__=="__main__":
    unittest.main()
