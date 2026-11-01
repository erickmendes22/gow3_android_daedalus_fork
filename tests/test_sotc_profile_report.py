#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check that diagnostic analysis does not mistake FPS for CPU/GPU profiling."""
import importlib.util
from pathlib import Path
import unittest

SRC=Path(__file__).resolve().parents[1]/'ports/sotc/android/analyze_frame_profile.py'
spec=importlib.util.spec_from_file_location("sotc_profile_report_test", SRC)
report=importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


class SotcProfileReportTest(unittest.TestCase):
    def test_fps_alone_must_not_claim_a_bottleneck(self):
        result=report.analyze(
            "[00:03:04] [PERF    ] Last minute: 20.1 FPS average, 575 frames over 50 ms\n"
            "Runtime: event flag 'PS4SyncEvent' waited 5s for 0x1\n")
        self.assertFalse(result["profile"])
        self.assertEqual(result["minute_fps"],[20.1])
        self.assertIn("no CPU/GPU bottleneck can be inferred",result["reason"])

    def test_real_split_cpu_and_readback_columns(self):
        line=("SOTC DRAW SPLIT per frame (120 frames): "
              "draw cpu 26.0 ms (idle spin 1.0; idle 1.0), "
              "cp cpu 21.0, recorder cpu 5.0; ops draw 5.0, indirect 1.0, "
              "dispatch 3.0, func 0.0, commands 0.1; "
              "bind 11.0 [buffers 2.0, textures 8.0, dma 1.0]; "
              "texture uploads 2.0 [hash 0.0, staging 0.0, copy 1.0 "
              "(5.0 MB in 1 copies, 0 of 2 MB+, 20 page faults), "
              "detile 0.0, record 0.0]; "
              "draw waits gpu 2.0, submit 1.0, recorder 0.0, frame 1.0; "
              "queue max 10; guest readback waits 15.0 "
              "[queue 1.0, submit 1.0, gpu 10.0, finish 3.0]\n")
        result=report.analyze(line+"SOTC FPS 20.1 at 180s; 6000 cmds/frame\n")
        self.assertTrue(result["profile"])
        self.assertEqual(result["per_frame_ms"]["draw_cpu_ms"],26.0)
        self.assertEqual(result["per_frame_ms"]["cp_cpu_ms"],21.0)
        self.assertEqual(result["per_frame_ms"]["bind_ms"],11.0)
        self.assertEqual(result["per_frame_ms"]["guest_readback_wait_ms"],15.0)
        self.assertIn("thread de desenho", " ".join(result["suspects"]))
        self.assertIn("BindResources", " ".join(result["suspects"]))
        self.assertEqual(result["fps_samples"],[20.1])

    def test_weighted_frame_counts(self):
        first=("SOTC DRAW SPLIT per frame (100 frames): draw cpu 25.0 ms "
               "(idle spin 0.0; idle 0.0), cp cpu 10.0, recorder cpu 2.0; "
               "ops draw 1.0, indirect 1.0, dispatch 1.0, func 0.0, commands 0.0; "
               "bind 5.0 [buffers 1.0, textures 3.0, dma 1.0]; "
               "draw waits gpu 1.0, submit 0.0, recorder 0.0, frame 1.0; "
               "guest readback waits 5.0 [queue 0.0, submit 0.0, gpu 1.0, finish 4.0]\n")
        second=first.replace("(100 frames)","(300 frames)").replace("draw cpu 25.0","draw cpu 15.0")
        result=report.analyze(first+second)
        self.assertEqual(result["frames"],400)
        self.assertEqual(result["per_frame_ms"]["draw_cpu_ms"],17.5)


if __name__=="__main__":
    unittest.main()
