"""Startup driver capability probing must not be mistaken for runtime image fallback.

Host-side source contracts only; actual hardware FPS requires a G720.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTANCE = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_instance.cpp").read_text()
IMAGE = (ROOT / "gpu/shadps4/video_core/texture_cache/image.cpp").read_text()
SERIAL = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_pipeline_serialization.cpp").read_text()


class MaliFormatUseTests(unittest.TestCase):
    def test_driver_capability_warnings_are_only_static_probes(self):
        method = INSTANCE[INSTANCE.index("void Instance::CollectImageFormatInfo()"):]
        self.assertIn('for (const auto& format : LiverpoolToVK::SurfaceFormats())', method)
        self.assertIn('for (const auto& format : LiverpoolToVK::DepthFormats())', method)
        self.assertNotIn('vmaCreateImage(', method[:method.index("void Instance::CollectToolingInfo")])

    def test_runtime_format_event_requires_real_image_construction(self):
        fragment = IMAGE[IMAGE.index('const bool is_mali = instance.GetPhysicalDevice()'):]
        before_create = fragment[:fragment.index('backing->image.Create(image_ci);')]
        self.assertIn('GOW3_MALI_FORMAT_RUNTIME guest=%s backing=%s', before_create)
        self.assertIn('vk::Format::eA2B10G10R10SnormPack32', before_create)
        self.assertIn('vk::Format::eD16UnormS8Uint', before_create)
        self.assertIn('count.fetch_add(1, std::memory_order_relaxed) < 4', before_create)
        self.assertIn('image_format_properties.result == vk::Result::eSuccess', before_create)
        self.assertNotIn('GOW3_MALI_FORMAT_RUNTIME', INSTANCE)

    def test_format_conversion_not_silently_reinterpreted(self):
        self.assertIn('vk::Format::eD24UnormS8Uint', INSTANCE)
        self.assertIn('vk::Format::eD32SfloatS8Uint', INSTANCE)
        self.assertNotIn('case vk::Format::eA2B10G10R10SnormPack32:', INSTANCE)

    def test_missing_shader_profile_keeps_old_generation(self):
        self.assertIn('status=restored-compatible-archive', SERIAL)
        self.assertIn('status=new-profile', SERIAL)
        self.assertIn('db.ArchiveIncompatibleCache()', SERIAL)
        self.assertNotIn('db.Clear();', SERIAL)


if __name__ == "__main__":
    unittest.main()
