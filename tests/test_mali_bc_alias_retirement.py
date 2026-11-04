"""Mali G720: safe BC surface retire never reinterprets mixed tiling or drops GPU writes."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
S=(ROOT/"gpu/shadps4/video_core/texture_cache/texture_cache.cpp").read_text()
SH=(ROOT/"tools/android/bionic/run-bionic.sh").read_text()
class AliasRetireTest(unittest.TestCase):
 def test_alias_guard_never_overridden(self):
  self.assertIn("a.pitch != b.pitch || a.tile_mode != b.tile_mode",S)
  self.assertIn("return {merged_image_id, -1, -1};",S)
  self.assertIn("if (can_retire_alias) FreeImage(cache_image_id);",S)
  self.assertIn("cache_image.tick_accessed_last != 0",S)
  self.assertIn("scheduler.IsFree(cache_image.tick_accessed_last)",S)
  self.assertIn("!cache_image.binding.is_target && !cache_image.binding.is_bound",S)
  self.assertIn("False(cache_image.flags & ImageFlagBits::GpuModified)",S)
 def test_only_mali_and_bc_one_sample_strict_tile_pair(self):
  self.assertIn("vendorID == 0x13B5",S)
  self.assertIn("old_info.props.is_block != image_info.props.is_block",S)
  self.assertIn("old_info.num_samples == 1 && image_info.num_samples == 1",S)
  self.assertIn("u32(old_info.tile_mode) == 8 && u32(image_info.tile_mode) == 13",S)
  self.assertIn("u32(old_info.tile_mode) == 13 && u32(image_info.tile_mode) == 8",S)
  self.assertIn("GOW3_MALI_BC_ALIAS_RETIRE=${GOW3_MALI_BC_ALIAS_RETIRE:-1}",SH)
 def test_no_disk_or_view_reinterpretation(self):
  self.assertIn("GOW3_TEXTURE_OVERLAP_LAYOUT_REJECT",S)
  self.assertIn("GOW3_BC_ALIAS_RETIRED",S)
  self.assertNotIn("IsVulkanFormatCompatible(b.pixel_format, a.pixel_format) || is_bc_layout_pair",S)
if __name__=="__main__":unittest.main()
