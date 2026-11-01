// SPDX-License-Identifier: GPL-2.0-or-later
// Real SotC fastpath header, exercised without a Vulkan device.
#include "../ports/sotc/android/vk_sotc_fastpaths.h"
#include <cassert>
#include <cstdint>
#include <vector>

struct FakeBinding {
    std::uint32_t binding, stride, inputRate, divisor;
};
struct FakeAttribute {
    std::uint32_t location, binding, format, offset;
};
int main() {
    using namespace SotcFastPath;
    GraphicsPipelineMemo<int,int> pipelines;
    assert(pipelines.NeedsBind(10, 55, 1, 0));
    assert(!pipelines.NeedsBind(10, 55, 1, 0)); // exact duplicate VkCmdBindPipeline
    assert(pipelines.NeedsBind(10, 56, 1, 0));  // new shader
    assert(pipelines.NeedsBind(10, 55, 1, 0));  // restore previous shader
    assert(pipelines.NeedsBind(10, 55, 1, 1));  // blit or render scope switched
    assert(pipelines.NeedsBind(10, 55, 2, 1));  // GPU submit
    assert(pipelines.NeedsBind(11, 55, 2, 1));  // recycled command buffer
    pipelines.Invalidate();
    assert(pipelines.NeedsBind(11, 55, 2, 1));  // forced unsafe-state reset

    VertexInputMemo<int,FakeBinding,FakeAttribute> vertex;
    std::vector<FakeBinding> bindings{{0,16,0,1}, {1,32,1,1}};
    std::vector<FakeAttribute> attrs{{0,0,44,0}, {1,1,45,8}};
    const auto needs = [&](int command, std::uint64_t tick, std::uint64_t epoch) {
        return vertex.NeedsSet(command,tick,epoch,
                               std::span<const FakeBinding>{bindings},
                               std::span<const FakeAttribute>{attrs});
    };
    assert(needs(10,1,0));
    assert(!needs(10,1,0));                  // no redundant vertex state update
    attrs[1].offset = 16;
    assert(needs(10,1,0));                   // same size, different attribute
    assert(!needs(10,1,0));
    bindings[0].stride = 64;
    assert(needs(10,1,0));
    bindings[0].stride = 16;
    assert(needs(10,1,0));                   // previous state restored
    attrs.pop_back();
    assert(needs(10,1,0));                   // shorter descriptor array
    assert(needs(10,1,1));                   // new rendering scope
    assert(needs(10,2,1));                   // new submit
    assert(needs(11,2,1));                   // different command buffer
    vertex.Invalidate();
    assert(needs(11,2,1));
    attrs.clear(); bindings.clear();
    assert(needs(11,2,1));                   // exact empty vertex-input state
    assert(!needs(11,2,1));
    return 0;
}
