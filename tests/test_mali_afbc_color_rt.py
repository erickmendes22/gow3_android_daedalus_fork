"""Mali AFBC image usage safety preflight, not a device FPS measurement.

PanVK's panvk_image_can_use_afbc explicitly rejects STORAGE_BIT. A native
ARM64 GPU compile is required in addition to these source-level checks.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
def read(path):
    return (ROOT / path).read_text(encoding="utf-8")

class MaliAfbcColorRtTests(unittest.TestCase):
    def test_opt_in_only_for_safe_mali_color_rt(self):
        image = read("gpu/shadps4/video_core/texture_cache/image.cpp")
        shell = read("tools/android/bionic/run-bionic.sh")
        self.assertIn("GOW3_MALI_AFBC_COLOR_RT", image)
        self.assertIn("vendorID == 0x13B5", image)
        self.assertIn('(!afbc || afbc[0] != \'0\')', image)
        for clause in ("!info.props.needs_storage", "!info.props.is_block",
                       "!info.props.is_volume", "info.num_samples == 1",
                       "info.num_bits <= 32", "ImageType::Color2D"):
            self.assertIn(clause, image)
        self.assertIn("if (afbc_color)", image)
        self.assertIn("usage |= vk::ImageUsageFlagBits::eStorage;", image)
        self.assertIn("GOW3_MALI_AFBC_COLOR_RT:-1", shell)
        self.assertIn("afbc_color_rt=$GOW3_MALI_AFBC_COLOR_RT", shell)

    def test_guest_storage_write_requests_storage_capable_backing(self):
        hdr = read("gpu/shadps4/video_core/texture_cache/image_info.h")
        ctor = read("gpu/shadps4/video_core/texture_cache/image_info.cpp")
        cache = read("gpu/shadps4/video_core/texture_cache/texture_cache.cpp")
        self.assertIn("u32 needs_storage : 1;", hdr)
        self.assertIn("props.needs_storage = desc.is_written;", ctor)
        self.assertIn("const bool storage_requested = desc.type == BindingType::Storage;", cache)
        self.assertIn("(!storage_requested ||", cache)
        self.assertIn("vk::ImageUsageFlagBits::eStorage", cache)
        self.assertIn("upgraded.props.needs_storage = 1;", cache)
        self.assertIn("image_id = ExpandImage(upgraded, image_id);", cache)
        self.assertIn("RegisterImage(new_image_id);", cache)
        self.assertIn("runtime.CopyImage(&src_image, &new_image);", cache)
        self.assertIn("FreeImage(image_id);", cache)
        self.assertIn("CountAfbcStorageUpgrade()", cache)

    def test_writable_block_textures_never_transcode_to_nonstorage_etc2(self):
        image = read("gpu/shadps4/video_core/texture_cache/image.cpp")
        start = image.index("const bool want_etc2 =")
        stop = image.index("const bool bc1 =", start)
        self.assertIn("!info.props.needs_storage", image[start:stop])
        self.assertIn("transcoded_bc_to_etc2 = true", image)
        self.assertIn("props.needs_storage = desc.is_written;", read(
            "gpu/shadps4/video_core/texture_cache/image_info.cpp"))

    def test_real_storage_image_may_never_lose_required_usage(self):
        # PanVK may reject speculative STORAGE for an otherwise sampled image,
        # but imageStore requires an image actually created with STORAGE usage.
        image = read("gpu/shadps4/video_core/texture_cache/image.cpp")
        fallback = image[image.index("const bool want_etc2 ="):]
        self.assertIn("!info.props.needs_storage &&", fallback)
        self.assertIn("(usage_flags & vk::ImageUsageFlagBits::eStorage)", fallback)
        self.assertIn("upgraded.props.needs_storage = 1;", read(
            "gpu/shadps4/video_core/texture_cache/texture_cache.cpp"))
        self.assertIn("feature_flags |= vk::FormatFeatureFlagBits2::eStorageImage;", image)
        self.assertEqual(
            image.count("FormatFeatureFlags(usage_flags, info.props.needs_storage)"), 3)


    def test_mali_driver_diagnostics_use_real_line_terminators(self):
        # Literal backslash-n merged successive Vulkan calls into one
        # logcat line and hid the source of 400+ ms allocation stalls.
        for path in (
            "gpu/shadps4/video_core/texture_cache/image.cpp",
            "gpu/shadps4/video_core/renderer_vulkan/vk_instance.cpp",
        ):
            source = read(path)
            self.assertNotIn(r"\\n", source, path)
        trace = read("gpu/shadps4/video_core/renderer_vulkan/vk_instance.cpp")
        self.assertIn(r"\n", trace)
        self.assertIn("GOW3_MALI_VMA_DRIVER_CALL", trace)

    def test_transfers_do_not_require_storage_usage(self):
        runtime = read("gpu/shadps4/video_core/renderer_vulkan/vk_runtime.cpp")
        clear = runtime[runtime.index("void Runtime::ClearImage("):
                        runtime.index("void Runtime::SetBackingSamples(", runtime.index("void Runtime::ClearImage("))]
        self.assertIn("vk::ImageLayout::eTransferDstOptimal", clear)
        self.assertIn("cmdbuf.clearColorImage(", clear)
        self.assertNotIn("vk::DescriptorType::eStorageImage", clear)
        copy = runtime[runtime.index("void Runtime::CopyImage("):
                       runtime.index("void Runtime::ClearImage(")]
        self.assertIn("vk::ImageLayout::eTransferSrcOptimal", copy)
        self.assertIn("vk::ImageLayout::eTransferDstOptimal", copy)
        self.assertIn("cmdbuf.copyImage(", copy)

    def test_counters_are_compact(self):
        stats = read("gpu/shadps4/video_core/renderer_vulkan/vk_mali_perf_stats.h")
        self.assertIn("afbc_candidates=%llu", stats)
        self.assertIn("afbc_storage_upgrades=%llu", stats)
        self.assertIn("CountAfbcCandidate()", stats)
        self.assertIn("CountAfbcStorageUpgrade()", stats)

if __name__ == "__main__":
    unittest.main()
