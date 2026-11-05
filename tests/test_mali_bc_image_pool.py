"""Mali BCn cache: only identical, retired VkImages and bounded device-local memory."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
S=(ROOT/"gpu/shadps4/video_core/texture_cache/image.cpp").read_text()
H=(ROOT/"gpu/shadps4/video_core/texture_cache/image.h").read_text()
I=(ROOT/"gpu/shadps4/video_core/renderer_vulkan/vk_instance.cpp").read_text()
RUN=(ROOT/"tools/android/bionic/run-bionic.sh").read_text()
class BcImagePoolTest(unittest.TestCase):
 def test_inflight_never_reused_and_device_match(self):
  self.assertIn("scheduler.DeferOperation([this, image_id]",(ROOT/"gpu/shadps4/video_core/texture_cache/texture_cache.cpp").read_text())
  self.assertIn("e.allocator == allocator && SameBcCreate(e.create, raw)",S)
  self.assertIn("a.mipLevels == b.mipLevels",S)
  self.assertIn("a.samples == b.samples",S)
  self.assertIn("a.format == b.format",S)
  self.assertIn("a.extent.width == b.extent.width",S)
  self.assertIn("a.usage == b.usage",S)
  self.assertIn("a.tiling == b.tiling",S)
 def test_ram_bound_and_flush_before_allocator(self):
  self.assertIn("BcPoolLimit = 128ULL * 1024 * 1024",S)
  self.assertIn("BcPoolEntryLimit = 64ULL * 1024 * 1024",S)
  self.assertIn("BcPoolHasBudget(allocator)",S)
  self.assertIn("budgets[i].usage * 10 > budgets[i].budget * 9",S)
  self.assertLess(I.index("FlushMaliBcImagePool(allocator)"),I.index("vmaDestroyAllocator(allocator)"))
  self.assertIn("size_bytes = std::exchange(other.size_bytes, 0);",H)
  self.assertIn("reused_from_pool = std::exchange(other.reused_from_pool, false);",H)
  self.assertIn("!backing->image.reused_from_pool",S)
  self.assertIn("GOW3_MALI_BC_IMAGE_POOL=${GOW3_MALI_BC_IMAGE_POOL:-1}",RUN)
 def test_original_path_is_recoverable(self):
  self.assertIn("(!option || option[0] != '0')",S) if False else None
  self.assertIn("return !option || option[0] != '0';",S)
  self.assertIn("if (!recycle_bc || !ReturnBcImage",S)
  self.assertIn("vmaCreateImage(allocator, &image_ci_unsafe",S)
if __name__=="__main__":
 unittest.main()
