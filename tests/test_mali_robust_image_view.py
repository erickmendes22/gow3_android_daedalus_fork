"""Cross-check the PanVK physical image/view contract.
Native compiler and Vulkan view compatibility are tested in the full APK job.
"""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class RobustImageViewTests(unittest.TestCase):
    def test_physical_validation_has_usage_format_and_bound_guards(self):
        h=(ROOT/"gpu/shadps4/video_core/texture_cache/robust_image_view.h").read_text()
        for token in ("NoSubresources", "InvalidAspect", "IncompatiblePhysicalFormat",
                      "UnsupportedShaderUsage", "InvalidStorageMapping",
                      "IsVulkanFormatCompatible", "mip_capacity - v.base_mip",
                      "layer_capacity - v.base_layer"):
            self.assertIn(token,h)

    def test_shader_only_mali_and_adreno_isolated(self):
        c=(ROOT/"gpu/shadps4/video_core/texture_cache/image_view.cpp").read_text()
        self.assertIn("vendorID == 0x13B5",c)
        self.assertIn("if (is_mali) {",c)
        self.assertIn("RobustImage::Validate(physical)",c)
        self.assertIn("if (shader_only && (info.is_storage || image.info.props.is_block))",c)
        self.assertIn("return;",c)
        self.assertIn("view_range.levelCount = check.mip_count;",c)
        self.assertIn("view_format == backing_format",c)

    def test_no_zero_usage_or_unsupported_storage_view(self):
        h=(ROOT/"gpu/shadps4/video_core/texture_cache/robust_image_view.h").read_text()
        self.assertIn("if (!v.view_usage", h)
        self.assertIn("v.storage && !(v.view_usage & vk::ImageUsageFlagBits::eStorage)", h)
        self.assertIn('!IsVulkanFormatCompatible(v.requested_format, v.backing_format)', h)
        source=(ROOT/"gpu/shadps4/video_core/texture_cache/image_view.cpp").read_text()
        self.assertIn("if (shader_only || info.is_storage)", source)

if __name__=="__main__":
    unittest.main()

