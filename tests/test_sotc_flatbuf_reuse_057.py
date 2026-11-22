#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""SotC 0.1.57: ensure repeated SRT stream copies are skipped only safely."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "ports/sotc/android/stage_sotc_flatbuf_reuse_057.py"
spec = importlib.util.spec_from_file_location("sotc_ubo", PATCH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class FlatbufTests(unittest.TestCase):
    def test_exact_renderer_src_patch(self):
        with tempfile.TemporaryDirectory() as work:
            base = Path(work) / "shadps4/video_core/renderer_vulkan"
            base.mkdir(parents=True)
            src = (
                "// SotcPerf::BindGraphicsPipeline SOTC_RT_MEMO\n"
                "const u32 ubo_size = stage.FlatBuf().size() * sizeof(u32);\n"
                + mod.ORIGINAL + "\n"
                "buffer_infos.emplace_back(vk_buffer.Handle(), offset, ubo_size);\n"
            )
            path = base / "vk_rasterizer.cpp"
            path.write_text(src)
            mod.patch(Path(work))
            got = path.read_text()
            for required in (
                "std::memcmp(line.contents.data(), flat, ubo_size) == 0",
                "line.tick == sotc_current_tick",
                "line.generation == sotc_current_wrap",
                "line.handle == sotc_current_handle",
                "line.contents.size() * sizeof(u32) == ubo_size",
                "slot.generation = vk_buffer.WrapGeneration()",
                "slot.tick = scheduler.CurrentTick()",
                "slot.contents.assign(flat, flat + ubo_size / sizeof(u32))",
                "const u64 offset = vk_buffer.Copy(flat, ubo_size, alignment);",
                "SOTC_FLATBUF_REUSE",
                "SOTC_FLATBUF_ADAPTIVE",
                "sotc_probe_queries++ & 32767ULL",
                "sotc_probe_hits * 100 >= 4096ULL * 6",
                "const bool memo_lookup = memo_eligible",
                "if (memo_lookup) {",
                "if (memo_hit && sotc_flatbuf_adaptive)",
                "SOTC FLATBUF REUSE:",
            ):
                self.assertIn(required, got)
            self.assertEqual(got.count("buffer_infos.emplace_back(vk_buffer.Handle(), offset, ubo_size);"), 1)
            with self.assertRaisesRegex(ValueError, "pinned Vulkan UBO copy changed"):
                mod.patch(Path(work))

    def test_adaptive_window_is_bounded_and_recovers(self):
        # Pure decision model for the C++ 4096/32768 sample guard.
        # Bypassing memo is an optimization choice, never a skipped upload.
        def run(hit_every):
            queries, hits, enabled = 0, 0, True
            active = 0
            for _ in range(32768 * 2):
                position = queries & 32767
                queries += 1
                if position == 0:
                    enabled, hits = True, 0
                elif position == 4096:
                    enabled = hits * 100 >= 4096 * 6
                if enabled:
                    active += 1
                    if (_ % hit_every) == 0:
                        hits += 1
            return active
        self.assertEqual(run(20), 4096 * 2) # 5% sampled: rest disabled
        self.assertEqual(run(8), 32768 * 2) # 12.5% sampled: memo remains enabled

    def test_rejects_missing_original_guard(self):
        with tempfile.TemporaryDirectory() as work:
            base = Path(work) / "shadps4/video_core/renderer_vulkan"
            base.mkdir(parents=True)
            (base / "vk_rasterizer.cpp").write_text(mod.ORIGINAL)
            with self.assertRaisesRegex(ValueError, "missing existing renderer safeguard"):
                mod.patch(Path(work))

    def test_cache_invalidation_contract(self):
        # Key comparison is exact, never a hash-only match. A wrap invalidates
        # ALL previous offsets even when identical bytes are uploaded again.
        line = {"data": b"\x01" * 128, "tick": 20, "wrap": 3, "handle": 777}
        def eligible(data: bytes, tick: int, wrap: int, handle: int):
            return (len(data) == len(line["data"]) and
                    data == line["data"] and tick == line["tick"] and
                    wrap == line["wrap"] and handle == line["handle"])
        self.assertTrue(eligible(line["data"], 20, 3, 777))
        self.assertFalse(eligible(line["data"], 21, 3, 777))
        self.assertFalse(eligible(line["data"], 20, 4, 777))
        self.assertFalse(eligible(line["data"], 20, 3, 778))
        self.assertFalse(eligible(line["data"][:-1] + b"\x02", 20, 3, 777))

if __name__ == "__main__":
    unittest.main()
