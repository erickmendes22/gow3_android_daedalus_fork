"""Vertex/index command fusion must preserve every Vulkan binding and indirect path."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
CPP=(ROOT/"gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text()
HDR=(ROOT/"gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.h").read_text()
DRAW=CPP.split("void Rasterizer::DrawRecord(",1)[1].split("void Rasterizer::DrawIndirect(",1)[0]
VERTEX=CPP.split("void Rasterizer::EmitVertexBuffers(",1)[1].split("void Rasterizer::ResolveVertexBuffers(",1)[0]
class VertexFusion(unittest.TestCase):
    def test_direct_draw_preserves_index_order_in_single_record(self):
        self.assertIn("EmitVertexBuffers(is_indexed);",DRAW)
        self.assertIn("ResolveIndexBuffer(index_offset);",DRAW)
        self.assertNotIn("EmitIndexBuffer();",DRAW)
        self.assertIn("void EmitVertexBuffers(bool include_index_buffer = false);",HDR)
        self.assertEqual(VERTEX.count("scheduler.Record("),1)
        for op in ("setVertexInputEXT", "bindVertexBuffers(", "bindVertexBuffers2(", "bindIndexBuffer("):
            self.assertIn("cmdbuf."+op,VERTEX)
        self.assertLess(VERTEX.index("cmdbuf.setVertexInputEXT("),VERTEX.index("cmdbuf.bindVertexBuffers("))
        self.assertLess(VERTEX.index("cmdbuf.bindVertexBuffers2("),VERTEX.index("cmdbuf.bindIndexBuffer("))
    def test_indirect_legacy_bind_unchanged(self):
        self.assertIn("void Rasterizer::BindIndexBuffer(u32 index_offset)",CPP)
        self.assertIn("    EmitIndexBuffer();",CPP)
        self.assertIn("void Rasterizer::EmitIndexBuffer()",CPP)
        self.assertIn("    EmitVertexBuffers();",CPP)
        self.assertIn("if (include_index_buffer)",VERTEX)
        self.assertIn("scheduler.ReserveRecordData(",VERTEX)
if __name__=="__main__": unittest.main()
