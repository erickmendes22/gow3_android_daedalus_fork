"""R13 native regression: reconstruct the camera from exact float constants
captured from GoW3 CUSA01623 (2026-10-19 22:00), not synthetic offsets.
Builds the header in a standalone C++ executable before any Android job.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

class R13NativeCamera(unittest.TestCase):
    def test_captured_view_projection_and_inverse_compile_and_validate(self):
        cpp=r"""
#include <cmath>
#include <cstdio>
#include "gpu/shadps4/video_core/renderer_vulkan/gow3_camera_layout.h"

int main() {
    // Captured shader 05756ef0a3a4414c slot=1 floats=184, offset=16
    const float recorded[32] = {
        1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1,
        -1.93218994f, -.085549064f, .203650191f, .203648642f,
        .000457424117f, 3.48428059f, .119944811f, .119943894f,
        .404904306f, -.41217351f, .971676469f, .971669078f,
        86.8912888f, -964.743835f, 264.933899f, 265.431885f
    };
    const auto v=Gow3CameraLayout::RecoverViewProjection(recorded,32,1);
    if (!v.valid) return 1;
    if (std::abs(v.projection[0]-1.97416f)>.005f ||
        std::abs(v.projection[1]-3.50962f)>.005f ||
        std::abs(v.near_plane-.497986f)>.001f) return 2;
    if (std::abs(v.position[0]+17.67675f)>.02f ||
        std::abs(v.position[1]-241.0541f)>.02f ||
        std::abs(v.position[2]+299.2223f)>.02f) return 3;
    if (!Gow3CameraLayout::InversePair(v.view,v.inverse) ||
        !Gow3CameraLayout::InversePair(v.inverse,v.view)) return 4;
    // Independent earlier 1200-frame capture from the SAME shader, genuine
    // camera rotation with stable world position. History must see a change.
    const float earlier[32] = {
        1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1,
        -1.92641294f, -.0862333775f, .204205185f, .204203621f,
         .000354632095f, 3.47399640f, .120652519f, .120651595f,
         .404891312f, -.413328439f, .971472323f, .971464932f,
        87.0151062f,-962.621643f,264.712341f,265.210327f
    };
    const auto previous=Gow3CameraLayout::RecoverViewProjection(earlier,32,1);
    if (!previous.valid) return 8;
    for (int i=0;i<3;++i)
        if (std::abs(v.position[i]-previous.position[i])>.02f) return 9;
    float difference=0.f;
    for (int i=0;i<12;++i)
        difference+=std::abs(v.view[i]-previous.view[i]);
    if (difference < 0.01f) return 10;
    if (Gow3CameraLayout::RecoverViewProjection(recorded,32,0).valid) return 5;
    float corrupt[32]; for(int i=0;i<32;++i) corrupt[i]=recorded[i];
    corrupt[16+14]=corrupt[16+15]+2.f;
    if (Gow3CameraLayout::RecoverViewProjection(corrupt,32,1).valid) return 6;
    // A 16:9 raw projection is not itself a valid world-to-clip camera.
    float projection[32]{};
    projection[16]=1.97478f; projection[21]=3.51071f;
    projection[26]=-1.f; projection[27]=-1.f; projection[30]=-.5f;
    if (Gow3CameraLayout::RecoverViewProjection(projection,32,1).valid) return 7;
    return 0;
}
"""
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"go3_camera_test.cpp"
            binary=Path(tmp)/"go3_camera_test"
            path.write_text(cpp,encoding="utf-8")
            cmd=["c++","-std=c++20","-O2","-Wall","-Wextra",
                 "-I",str(ROOT),str(path),"-o",str(binary)]
            build=subprocess.run(cmd,capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stdout+build.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_actual_gsr2_camera_scanning_precedes_legacy_six_buffer_cap(self):
        src=(ROOT/"gpu/shadps4/video_core/renderer_vulkan/vk_camera_motion.cpp").read_text()
        self.assertIn("RecoverViewProjection(",src)
        self.assertLess(src.index("RecoverViewProjection("),
                        src.index("if (++frame_scanned_buffers > 6) return;"))
        self.assertIn("frame_pose_votes >= 2",src)
        self.assertIn("GOW3_CAMERA_VERIFIED_VP",src)
        # Never enable history with fake camera matrices.
        up=(ROOT/"gpu/shadps4/video_core/renderer_vulkan/vk_temporal_upscaler.cpp").read_text()
        self.assertIn("const bool temporal_ready = camera_motion.Ready();",up)
        self.assertIn(".reset = reset || !temporal_ready,",up)

    def test_r13_single_gated_build(self):
        wf=(ROOT/".github/workflows/bionic-apk.yml").read_text()
        self.assertIn("r14-build-trigger.txt",wf)
        self.assertIn("fix/bionic-r14-gsr2-history-camera-guard-20261019",wf)
        self.assertIn("cancel-in-progress: true",wf)

if __name__=="__main__":
    unittest.main()
