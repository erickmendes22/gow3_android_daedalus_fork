"""Compile the camera detector against synthetic guest matrices (no Vulkan needed)."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "gpu/shadps4/video_core/renderer_vulkan/gow3_camera_layout.h"

class CameraLayoutTests(unittest.TestCase):
    def test_detects_inverse_view_and_projection_and_rejects_bad_history(self):
        compiler = shutil.which("c++") or shutil.which("g++")
        if not compiler:
            self.skipTest("C++ compiler unavailable")
        source = r'''
#include <array>
#include <cassert>
#include <algorithm>
#include "gow3_camera_layout.h"
using namespace Gow3CameraLayout;
int main() {
    std::array<float,96> constants{};
    const std::array<float,16> view{
        1,0,0,-3, 0,1,0,2, 0,0,1,-9, 0,0,0,1
    };
    const std::array<float,16> inv{
        1,0,0,3, 0,1,0,-2, 0,0,1,9, 0,0,0,1
    };
    const std::array<float,16> proj{
        1.5f,0,0,0, 0,2.4f,0,0, 0,0,1.001f,-0.1f, 0,0,1,0
    };
    std::copy(view.begin(),view.end(),constants.begin());
    std::copy(inv.begin(),inv.end(),constants.begin()+16);
    std::copy(proj.begin(),proj.end(),constants.begin()+64);
    auto pose = FindPose(constants.data(), constants.size());
    auto lens = FindProjection(constants.data(), constants.size());
    assert(pose.valid && lens.valid);
    assert(pose.view_offset == 0 && pose.inverse_offset == 16);
    assert(lens.offset == 64);
    assert(InversePair(pose.view,pose.inverse));
    assert(lens.projection[1] > 2.3f);
    // Even a seemingly plausible rigid transform cannot pass without inverse.
    constants[16+3] = 7.0f;
    assert(!FindPose(constants.data(),constants.size()).valid);
    // Neither an uninitialized nor a zero buffer may create "valid motion".
    std::array<float,96> zeros{};
    assert(!FindPose(zeros.data(),zeros.size()).valid);
    assert(!FindProjection(zeros.data(),zeros.size()).valid);
    // Matrix layout may be column-major in CUSA01715 guest vertex buffers.
    for (int block: {0,16,64}) {
        std::array<float,16> old{};
        std::copy_n(constants.begin()+block,16,old.begin());
        for (int r=0;r<4;r++) for (int c=0;c<4;c++)
            constants[block+r*4+c]=old[c*4+r];
    }
    // Restore inverse translation before interpreting the transposed matrix.
    constants[16+3*4+0] = 3.0f;
    assert(FindPose(constants.data(),constants.size()).valid);
    assert(FindProjection(constants.data(),constants.size()).valid);
}
'''
        with tempfile.TemporaryDirectory() as temp:
            src = Path(temp) / "test.cpp"
            binary = Path(temp) / "test"
            src.write_text(source)
            subprocess.run([compiler, "-std=c++20", "-O2",
                "-I", str(HEADER.parent), str(src), "-o", str(binary)],
                check=True, capture_output=True, text=True)
            subprocess.run([str(binary)], check=True, capture_output=True, text=True)

if __name__ == "__main__":
    unittest.main()
