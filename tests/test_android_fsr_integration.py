"""Prevent packaging regressions in GoW3 Android graphics settings."""
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import launch_env
import patches


class AndroidFsrIntegrationTests(unittest.TestCase):
    def test_no_fsr_and_old_new_native_resolution_choices(self):
        ini = (ROOT / "tools/android/config/gow3-default.ini").read_text()
        ui = (ROOT / "android-launcher/app/src/main/java/com/gow3/android/data/LaunchParams.kt").read_text()
        java = (ROOT / "android-launcher/app/src/main/java/ro/cobrabm/fexdroid/SettingsDialog.java").read_text()
        run = (ROOT / "tools/android/device/run-gow3.sh").read_text()
        self.assertIn("upscaler=off", ini)
        self.assertIn("render_resolution=720p", ini)
        self.assertIn('key = "render_resolution"', ui)
        self.assertNotIn('key = "upscaler"', ui)
        self.assertNotIn('key = "preset"', ui)
        values = ("240p", "360p", "424p", "480p", "540p", "720p",
                  "900p", "native", "1440p", "1800p", "4K")
        for size in values:
            self.assertEqual(ui.count('LaunchOption("' + size + '",'), 1)
            self.assertIn('"' + size + '"', java)
        for duplicate in ("1280x720", "854x480", "960x540", "752x424",
                          "640x360", "426x240"):
            self.assertNotIn('LaunchOption("' + duplicate + '",', ui)
        self.assertIn('key = "render_resolution"', ui)
        self.assertEqual(java.count("private static final String[] RESOLUTION_NAMES"), 1)
        self.assertIn("export GOW3_UPSCALER=none", run)
        self.assertIn("unset GOW3_ANDROID_FSR_FIXED_OUTPUT", run)
        self.assertNotIn("GOW3_FSR_STARTUP", run)

    def test_android_fsr_device_matches_bloodborne_enabled_features(self):
        # Compare to ducvd89/Bloodborne-Android android-0.5.2, same
        # FSR-Vulkan submodule c64f093404125e960813f95f1996c14780f0dd69.
        root = ROOT / "gpu/shadps4/video_core/renderer_vulkan"
        instance = (root / "vk_instance.cpp").read_text()
        upscaler = (root / "vk_temporal_upscaler.cpp").read_text()
        for feature in (
            ".vulkanMemoryModel = vk12_features.vulkanMemoryModel",
            ".vulkanMemoryModelDeviceScope = vk12_features.vulkanMemoryModelDeviceScope",
            ".computeFullSubgroups = vk13_features.computeFullSubgroups",
        ):
            with self.subTest(feature=feature):
                self.assertIn(feature, instance)
        self.assertIn("instance.IsStorageImageWriteWithoutFormatEnabled() ? VK_TRUE : VK_FALSE",
                      upscaler)
        self.assertNotIn("device_info.shaderStorageImageWriteWithoutFormatEnabled = VK_TRUE",
                         upscaler)

    def test_arm64_fmt_dynamic_dependency_is_not_required(self):
        cmake = (ROOT / "gpu/CMakeLists.txt").read_text()
        build = (ROOT / "tools/android/build/build_arm64.sh").read_text()
        self.assertIn('set(GOW3_FMT_TARGET fmt::fmt-header-only)', cmake)
        self.assertIn('UND.*_ZN3fmt3v[0-9]+', build)

    def test_android_virtual_save_dialog_and_720p_ui_target(self):
        overlay = (ROOT / "gpu/shim/gow3_overlay.cpp").read_text()
        header = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_temporal_upscaler.h").read_text()
        self.assertIn("ChoicePadMask()", overlay)
        self.assertIn("const unsigned pressed = held & ~choice_pad_held", overlay)
        self.assertIn("(w == target_width && h == target_height)", header)

    def test_android_720p_texture_targets_and_real_scaling(self):
        root = ROOT / "gpu/shadps4/video_core/renderer_vulkan"
        scene = (root / "vk_scene_resolution.cpp").read_text()
        header = (root / "vk_scene_resolution.h").read_text()
        raster = (root / "vk_rasterizer.cpp").read_text()
        self.assertIn('guest_size = {1280, 720}', scene)
        self.assertIn('size = guest_size;', scene)
        self.assertIn('(w == 640 && h == 360)', scene)
        self.assertIn('SizeDivisor(i, size, guest_size)', scene)
        self.assertIn('SizeDivisor(image.info, size, guest_size)', scene)
        self.assertIn('size != guest_size', header)
        self.assertIn('scene_targets->GuestSize().width', raster)
        self.assertIn('float(size.width) / float(guest.width)', raster)
        self.assertNotIn('target_scale = {float(size.width) / 1920.0f', raster)

    def test_guest_dimensions_are_observed_not_assumed(self):
        root = ROOT / "gpu/shadps4/video_core/renderer_vulkan"
        scene = (root / "vk_scene_resolution.cpp").read_text()
        raster = (root / "vk_rasterizer.cpp").read_text()
        fsr = (root / "vk_temporal_upscaler.cpp").read_text()
        self.assertIn('ObserveGuestScene(u32 width, u32 height)', scene)
        self.assertIn('scene_targets->ObserveGuestScene(', raster)
        self.assertIn('GOW3_SCENE_ACTUAL passes=', raster)
        self.assertIn('GOW3_GBUFFER_ACTUAL guest=', scene)
        self.assertIn('vk::Format::eR8G8B8A8Srgb', fsr)
        self.assertIn('GOW3_FSR_UI_CANDIDATE', fsr)
        self.assertIn('android_hud_transition', fsr)
        self.assertIn('depth != camera_motion.Depth()', fsr)

    def test_android_fsr_only_triggers_on_scene_hud_depth_transition(self):
        root = ROOT / "gpu/shadps4/video_core/renderer_vulkan"
        source = (root / "vk_temporal_upscaler.cpp").read_text()
        camera = (root / "vk_camera_motion.cpp").read_text()
        self.assertIn('android ? android_hud_transition', source)
        self.assertIn('depth != camera_motion.Depth()', source)
        self.assertIn('GOW3_CAMERA_VERIFIED pair=1 projection=1', camera)

    def test_android_fsr_forward_renderer_composites_at_display_boundary(self):
        camera = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_camera_motion.cpp").read_text()
        fsr = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_temporal_upscaler.cpp").read_text()
        header = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_temporal_upscaler.h").read_text()
        raster = (ROOT / "gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text()
        self.assertIn("upscaler->OnDisplayBoundary(cb_descs[0].first)", raster)
        self.assertIn("void TemporalUpscaler::OnDisplayBoundary(", fsr)
        self.assertIn("void OnDisplayBoundary(VideoCore::ImageId color);", header)
        self.assertIn("const auto guest = scene_targets->GuestSize();", raster)
        self.assertNotIn("std::popcount(key.mrt_mask) >= 5 && db_desc.first", raster)
        self.assertIn('state=MOTION_UNVERIFIED action=NATIVE_PRESENT', fsr)
        self.assertNotIn('state=MOTION_UNVERIFIED action=SPATIAL_ONLY', fsr)
        # A missing camera must never mark UI compositing as complete or
        # redirect the guest display buffer through RunUiOnly.
        scaled = fsr.split('void TemporalUpscaler::RunScaled() {', 1)[1]
        fallback = scaled.split('if (!EnsureResources(w, h, ow, oh, false))', 1)[0]
        self.assertNotIn('RunUiOnly(', fallback.split('state=MOTION_UNVERIFIED', 1)[1])
        self.assertIn('camera_motion.RecordMotion(cmdbuf, depth_view, *motion_view, w, h)', fsr)
        self.assertIn("reprojection ? camera_motion.Near() : 0.1f", fsr)
        self.assertNotIn('if (std::getenv("GOW3_ANDROID_FSR_FIXED_OUTPUT")) return;', camera)
        self.assertIn('GOW3_CAMERA_VERIFIED pair=1 projection=1', camera)
        self.assertIn('GOW3_FSR_STATUS state=CONTEXT_FAILED', fsr)
        self.assertIn('"TEMPORAL_HISTORY_ACTIVE" : "DISPATCH_RECORDED"', fsr)
        self.assertIn('GOW3_FSR_STATUS state=TEMPORAL_PRESENTED', fsr)
        self.assertIn('GOW3_FSR_CAPS query=', fsr)
        self.assertIn('const VideoCore::ImageId scene = ldr_target;', fsr)
        self.assertIn('android && native_viewport && camera_motion.Depth()', fsr)
        self.assertIn('if (std::getenv("GOW3_ANDROID_FSR_FIXED_OUTPUT") && !camera_motion.Ready()) {', fsr)
        self.assertIn('Leave guest UI, color and display untouched', fsr)
        self.assertNotIn("GOW3_CAMERA_BUFFER sample=", raster)
        self.assertNotIn("GOW3_FSR_TOPOLOGY", raster)

    def test_camera_layout_is_scanned_not_bloodborne_hardcoded(self):
        base = ROOT / "gpu/shadps4/video_core/renderer_vulkan"
        camera = (base / "vk_camera_motion.cpp").read_text()
        raster = (base / "vk_rasterizer.cpp").read_text()
        detector = (base / "gow3_camera_layout.h").read_text()
        self.assertIn('Gow3CameraLayout::FindPose(data, float_count)', camera)
        self.assertIn('Gow3CameraLayout::FindProjection(data, float_count)', camera)
        self.assertIn('frame_pose_votes >= 2', camera)
        self.assertIn('const auto* data = constant_ring->Data(ring->offset);', raster)
        self.assertIn('camera_motion->OnConstants(reinterpret_cast<const float*>(data),', raster)
        self.assertNotIn('OnConstants(reinterpret_cast<const float*>(ring->address),', raster)
        self.assertIn('std::strcmp(active_upscaler, "gsr2") == 0', raster)
        self.assertIn('ring->size >= 64', raster)
        self.assertIn('InversePair(a, b) && InversePair(b, a)', detector)

    def test_shadow_toggle_semantics(self):
        from launch_env import disable_shadows_requested
        self.assertTrue(disable_shadows_requested({"disable_dynamic_shadows": "1"}))
        self.assertFalse(disable_shadows_requested({"disable_dynamic_shadows": "0"}))
        self.assertTrue(disable_shadows_requested({"effect_dynamic_shadows": "0"}))
        self.assertFalse(disable_shadows_requested({"effect_dynamic_shadows": "1"}))
        self.assertFalse(disable_shadows_requested({
            "disable_dynamic_shadows": "0", "effect_dynamic_shadows": "0"}))

    def test_verified_shadow_patch_exists(self):
        metas = ET.parse(ROOT / "patches/God_of_War_III_Remastered.xml").getroot().iter("Metadata")
        matching = [meta for meta in metas if meta.get("Name") == "Disable Dynamic Shadows"]
        self.assertEqual(len(matching), 1)
        lines = list(matching[0].iter("Line"))
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].get("Address"), "0x005b739b")
        self.assertEqual(lines[0].get("Value"), "eb32")

    def test_android_launch_gates_shadows_and_disables_fsr(self):
        verified = "6e72330e9092e5164049b865e5568f2d450904001a73fe0a2f4b39194c195b3c"
        fixture = ROOT / "patches/God_of_War_III_Remastered.xml"
        profile = ({"CUSA01715"}, fixture, "01.02", "God of War III")
        def identity(sha):
            return {"reason": "validated", "title_id": "CUSA01715",
                    "app_version": "01.02", "eboot_sha256": sha,
                    "eboot_matches": True}
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "gow3.ini"
            state = Path(tmp) / "graphics_state.json"
            config.write_text("upscaler=fsr3\npreset=3\nrender_resolution=640x360\n"
                              "effect_dynamic_shadows=0\n")
            env = {"GOW3_ANDROID_PORT": "1"}
            with patch.object(patches, "patch_profile_status", return_value=identity(verified)), \
                    patch.object(patches, "game_profile", return_value=profile):
                result = launch_env.derive(Path(tmp), config, state, env)
            self.assertEqual(result["updates"]["GOW3_UPSCALER"], "none")
            self.assertEqual(result["updates"]["GOW3_PATCH_INPUT_RES"], "640x360")
            self.assertEqual(result["updates"]["GOW3_RESOLUTION_STATUS"], "verified-direct-game-patch")
            self.assertIn("Resolution Patch - 720p", result["patch_names"])
            self.assertIn("Disable Dynamic Shadows", result["patch_names"])
            self.assertIn("upscaler=off", config.read_text())
            with patch.object(patches, "patch_profile_status", return_value=identity("0"*64)), \
                    patch.object(patches, "game_profile", return_value=profile):
                not_verified = launch_env.derive(Path(tmp), config, state, env)
            self.assertNotIn("Disable Dynamic Shadows", not_verified["patch_names"])
            self.assertNotIn("GOW3_PATCH_INPUT_RES", not_verified["updates"])
            self.assertEqual(not_verified["updates"]["GOW3_UPSCALER"], "none")


if __name__ == "__main__":
    unittest.main()
