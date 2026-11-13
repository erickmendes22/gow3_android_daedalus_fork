// The opaque fragment fast path must never change a shader that can
// discard pixels, write a buffer/image, or change depth/sample coverage.
// Standalone host unit test: c++ -std=c++20 -O2 -Igpu/shadps4
// -Igpu/third_party/sirit/externals/SPIRV-Headers/include tests/test_mali_gpu_early_z.cpp -o /tmp/mali_early_z_test
#include <cassert>
#include <cstdint>
#include <vector>
#include <spirv/unified1/spirv.h>
#include "video_core/renderer_vulkan/vk_mali_early_z.h"

using uint = uint32_t;
static uint Op(uint wc, uint op) { return (wc << 16) | op; }

static std::vector<uint> Fragment(bool storage_write = false) {
    return {
        SpvMagicNumber, 0x00010500, 0, 32, 0,
        Op(5, SpvOpEntryPoint), SpvExecutionModelFragment, 1, 0x6e69616d, 0,
        Op(3, SpvOpExecutionMode), 1, SpvExecutionModeOriginUpperLeft,
        Op(4, SpvOpTypePointer), 5,
        storage_write ? SpvStorageClassStorageBuffer : SpvStorageClassOutput, 4,
        Op(4, SpvOpVariable), 5, 6,
        storage_write ? SpvStorageClassStorageBuffer : SpvStorageClassOutput,
        Op(3, SpvOpStore), 6, 7
    };
}

int main() {
    std::vector<uint> out{};
    auto opaque = Fragment();
    assert(Vulkan::MaliEarlyZ::Transform(opaque, out));
    assert(out.size() == opaque.size() + 3);
    assert(out[14] == Op(3, SpvOpExecutionMode));
    assert(out[15] == 1 && out[16] == SpvExecutionModeEarlyFragmentTests);
    assert(!Vulkan::MaliEarlyZ::Transform(out, out)); // already modified
    auto side_effect = Fragment(true);
    assert(!Vulkan::MaliEarlyZ::Transform(side_effect, out));
    auto drop = Fragment();
    drop.push_back(Op(1, SpvOpKill));
    assert(!Vulkan::MaliEarlyZ::Transform(drop, out));
    auto demote = Fragment();
    demote.push_back(Op(1, SpvOpDemoteToHelperInvocationEXT));
    assert(!Vulkan::MaliEarlyZ::Transform(demote, out));
    auto atomic = Fragment();
    atomic.push_back(Op(4, SpvOpAtomicIAdd));
    atomic.insert(atomic.end(), {12, 14, 15});
    assert(!Vulkan::MaliEarlyZ::Transform(atomic, out));
    auto image = Fragment();
    image.push_back(Op(4, SpvOpImageWrite));
    image.insert(image.end(), {12, 14, 15});
    assert(!Vulkan::MaliEarlyZ::Transform(image, out));
    auto frag_depth = Fragment();
    frag_depth.insert(frag_depth.end(), {Op(4, SpvOpDecorate), 6,
                                        SpvDecorationBuiltIn, SpvBuiltInFragDepth});
    assert(!Vulkan::MaliEarlyZ::Transform(frag_depth, out));
    auto replaced = Fragment();
    replaced.insert(replaced.end(), {Op(3, SpvOpExecutionMode), 1,
                                     SpvExecutionModeDepthReplacing});
    assert(!Vulkan::MaliEarlyZ::Transform(replaced, out));
    auto other_stage = Fragment();
    other_stage[6] = SpvExecutionModelVertex;
    assert(!Vulkan::MaliEarlyZ::Transform(other_stage, out));
    auto corrupt = Fragment();
    corrupt[5] = Op(0, SpvOpEntryPoint);
    assert(!Vulkan::MaliEarlyZ::Transform(corrupt, out));
    return 0;
}
