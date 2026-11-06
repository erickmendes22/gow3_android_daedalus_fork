"""Mali R32 pool is exact-create, bounded, and independent from the proven BC pool."""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
S=(ROOT/"gpu/shadps4/video_core/texture_cache/image.cpp").read_text()
RUN=(ROOT/"tools/android/bionic/run-bionic.sh").read_text()
INST=(ROOT/"gpu/shadps4/video_core/renderer_vulkan/vk_instance.cpp").read_text()
class Rgba128Pool(unittest.TestCase):
 def test_independent_memory_quota_and_logging(self):
  for key in ["Rgba128PoolLimit = 64ULL * 1024 * 1024",
              "Rgba128PoolEntryLimit = 32ULL * 1024 * 1024",
              "Rgba128PoolMaxEntries = 24",
              "BcPoolLimit = 128ULL * 1024 * 1024",
              "GetRgba128Pool()",
              'rgba128 ? "RGBA128" : "BC"',
              "ImagePoolFor(raw)","PoolLimit(raw)",
              "BcPoolHasBudget(allocator)"]:
   self.assertIn(key,S)
 def test_no_alias_or_live_image_recycling(self):
  self.assertIn("a.format == b.format",S)
  self.assertIn("a.samples == b.samples",S)
  self.assertIn("e.allocator == allocator && SameBcCreate(e.create, raw)",S)
  self.assertIn("scheduler.DeferOperation([this, image_id]",
   (ROOT/"gpu/shadps4/video_core/texture_cache/texture_cache.cpp").read_text())
  self.assertIn("for (auto* target : {&GetBcPool(), &GetRgba128Pool()})",S)
  self.assertLess(INST.index("FlushMaliBcImagePool(allocator)"),INST.index("vmaDestroyAllocator(allocator)"))
  self.assertIn("!backing->image.reused_from_pool",S)
 def test_mali_only_reversible(self):
  self.assertIn("GOW3_MALI_RGBA128_IMAGE_POOL=${GOW3_MALI_RGBA128_IMAGE_POOL:-1}",RUN)
  self.assertIn("GOW3_MALI_BC_IMAGE_POOL=${GOW3_MALI_BC_IMAGE_POOL:-1}",RUN)
  self.assertIn('rgba128_pool=$GOW3_MALI_RGBA128_IMAGE_POOL',RUN)
  self.assertIn("rgba128_pool_enabled && image_ci.format == vk::Format::eR32G32B32A32Uint",S)
  self.assertIn("instance.GetPhysicalDevice().getProperties().vendorID == 0x13B5",S)
if __name__=="__main__": unittest.main()
