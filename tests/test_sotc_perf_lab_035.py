#!/usr/bin/env python3
"""SotC 0.1.35: native flags, GUI wiring, safety defaults and exclusion tests."""
import json
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
O=json.loads((ROOT/"ports/sotc/android/sotc_perf_lab_035.json").read_text())
UI=(ROOT/"android-launcher/app/src/main/java/com/gow3/android/ui/SotcScreen.kt").read_text()
JAVA=(ROOT/"android-launcher/app/src/main/java/ro/cobrabm/fexdroid/GameActivity.java").read_text()
SH=(ROOT/"ports/sotc/android/run-sotc-bionic.sh").read_text()
PKG=(ROOT/"ports/sotc/android/package_sotc_runtime.py").read_text()
RENDERER=ROOT/"upstream-sotc/gpu/shadps4/video_core"

class SotcPerfLab(unittest.TestCase):
    def test_wiring(self):
        all_flags=O["toggles"]+O["choices"]
        self.assertEqual(len(all_flags),26)
        self.assertEqual(len(set(x["key"] for x in all_flags)),26)
        self.assertEqual(len(set(x["env"] for x in all_flags)),26)
        for x in all_flags:
            k,e,d=x["key"],x["env"],x["def"]
            with self.subTest(k=k):
                self.assertIn(f'values["{k}"]?:"{d}"',UI)
                self.assertIn(f'save("{k}"',UI)
                self.assertIn(f'"{k}"',JAVA)
                self.assertIn(f'env.put("{e}"',JAVA)
                self.assertIn(f'{k}={d}',PKG)
                if x["type"]=="toggle":
                    self.assertIn("export "+e+"=",SH)
                    self.assertIn("Invalid "+e,SH)
                elif k not in ("sotc_pipeline_workers","sotc_rb_stream_max_kb"):
                    self.assertIn("export "+e+"=",SH)
                    self.assertIn("Invalid "+e,SH)
        self.assertIn("SOTC_RB_STREAM_MAX_KB",SH)
        self.assertIn("128|256|512|1024|2048|4096",SH)
        self.assertIn("export SOTC_FLUSH_EVERY=256",SH)
        self.assertIn("SOTC_PIPELINE_WORKERS",SH)

    def test_preserve_good_settings_and_exclude_unsafe(self):
        for s in ("sotc_readbacks=2","sotc_rb_stream=1","sotc_rb_stream_max_kb=512",
                  "sotc_vm_range_cache=1","sotc_record_thread=0","sotc_rb_async=0",
                  "sotc_fast_bind=0","sotc_async_shaders=0"):
            self.assertIn(s,PKG)
        for v in ("export SOTC_UPLOAD_BUDGET_MB=0","export SOTC_VM_RANGE_CACHE=",
                  "export BB_READBACKS=","export SOTC_RB_AHEAD=",
                  "export SOTC_FLUSH_US=","export SOTC_SHADOW_STAGGER="):
            self.assertIn(v,SH)
        forbidden=set(O["exclusions"])
        self.assertIn("SOTC_CP_FREE_TASKS",forbidden)
        self.assertIn("SOTC_RB_HOT",forbidden)
        for x in O["toggles"]+O["choices"]:
            self.assertNotIn(x["env"],forbidden)

    @unittest.skipUnless(RENDERER.is_dir(),"Requires pinned original SotC renderer")
    def test_existing_real_native_implementations(self):
        native="".join(p.read_text(errors="replace") for p in RENDERER.rglob("*.cpp"))
        for x in O["toggles"]+O["choices"]:
            self.assertIn('"'+x["env"]+'"',native,x["env"]+" missing in C++")
        self.assertIn("GatherDownloads(",native)
        self.assertIn("ApplyDownloads(",native)

if __name__=="__main__":
    unittest.main()
