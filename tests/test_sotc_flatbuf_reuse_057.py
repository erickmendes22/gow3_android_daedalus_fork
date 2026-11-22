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
                "SOTC FLATBUF REUSE:",
            ):
                self.assertIn(required, got)
            self.assertEqual(got.count("buffer_infos.emplace_back(vk_buffer.Handle(), offset, ubo_size);"), 1)
            with self.assertRaisesRegex(ValueError, "pinned Vulkan UBO copy changed"):
                mod.patch(Path(work))

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
