"""R18: Native AA must not initialize GSR2's scene/display routing.

Both Native and GSR2 reconstruction need correct texture-cache ownership.
Native has no GSR2 dispatch; leaving the provider enabled only enables its
GPU hooks and forces a spurious 720p PS4 resolution patch.
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import launch_env
import patches

class R18NativePath(unittest.TestCase):
    def plan(self, preset, resolution="native"):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp)
            config=base/"gow3.ini"
            config.write_text(f"upscaler=gsr2\npreset={preset}\nrender_resolution={resolution}\n",encoding="utf-8")
            identity={"title_id":"CUSA01623","app_version":"01.02",
                      "eboot_sha256":patches.CUSA01715_0102_ANDROID_SHA,
                      "eboot_matches":True,"reason":"validated"}
            with patch.object(patches,"patch_profile_status",return_value=identity):
                plan=launch_env.derive(base,config,base/"state.json",{"GOW3_ANDROID_PORT":"1"})
            return plan,config.read_text(encoding="utf-8")

    def test_native_aa_has_no_dispatch_or_forced_720p_patch(self):
        plan,persisted=self.plan("0")
        u=plan["updates"]
        self.assertEqual(u["GOW3_UPSCALER"],"none")
        self.assertEqual(u["GOW3_UPSCALER_SOURCE"],"native-aa-1to1-no-gsr2")
        self.assertNotIn("GOW3_PATCH_INPUT_RES",u)
        self.assertNotIn("Resolution Patch - 720p",plan["patch_names"])
        self.assertIn("Bug Fix - Texture Corruption Fix",plan["patch_names"])
        self.assertIn("upscaler=gsr2\npreset=0\n",persisted)

    def test_explicit_720p_is_preserved_without_gsr2_routing(self):
        plan,_=self.plan("0","720p")
        self.assertEqual(plan["updates"]["GOW3_UPSCALER"],"none")
        self.assertIn("Resolution Patch - 720p",plan["patch_names"])
        self.assertNotIn("GOW3_PATCH_INPUT_RES",plan["updates"])

    def test_reduced_gsr2_presets_remain_selected(self):
        for preset in ("1","2","3","4"):
            with self.subTest(preset=preset):
                plan,_=self.plan(preset,"720p")
                self.assertEqual(plan["updates"]["GOW3_UPSCALER"],"gsr2")
                self.assertEqual(plan["updates"]["GOW3_PATCH_INPUT_RES"],"1280x720")
                self.assertIn("Resolution Patch - 720p",plan["patch_names"])

    def test_stencil_reallocation_never_uses_old_depth_reference(self):
        cpp=(ROOT/"gpu/shadps4/video_core/texture_cache/texture_cache.cpp").read_text(encoding="utf-8")
        fn=cpp.split("ImageView& TextureCache::FindDepthTarget(",1)[1].split(
            "void TextureCache::RefreshImage(",1)[0]
        allocation=fn.index("stencil_id = slot_images.insert(")
        reload=fn.index("slot_images[image_id].image_uid")
        return_view=fn.index("return slot_images[image_id].FindView(")
        self.assertLess(allocation,reload)
        self.assertLess(reload,return_view)
        self.assertNotIn("AssociateDepth(image_id, image.image_uid)",fn)
        self.assertNotIn("return image.FindView(",fn)

    def test_depth_source_reference_is_reloaded_after_slotvector_growth(self):
        cpp=(ROOT/"gpu/shadps4/video_core/texture_cache/texture_cache.cpp").read_text(encoding="utf-8")
        slot=(ROOT/"gpu/shadps4/common/slot_vector.h").read_text(encoding="utf-8")
        fn=cpp.split("ImageId TextureCache::ResolveDepthOverlap(",1)[1].split(
            "std::tuple<ImageId, int, int> TextureCache::ResolveOverlap(",1)[0]
        insert_pos=fn.index("slot_images.insert(")
        refresh_pos=fn.index("auto& source_after_insert = slot_images[cache_image_id];")
        use_pos=fn.index("runtime.CopyColorAndDepth(&source_after_insert, &new_image);")
        self.assertLess(insert_pos,refresh_pos)
        self.assertLess(refresh_pos,use_pos)
        self.assertNotIn("runtime.CopyColorAndDepth(&cache_image, &new_image)",fn)
        self.assertIn("T(std::move(old_value))",slot)
        self.assertIn("delete[] values;",slot)

if __name__=="__main__":
    unittest.main()
