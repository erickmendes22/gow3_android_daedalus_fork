// SPDX-License-Identifier: GPL-2.0-or-later
#include "video_core/renderer_vulkan/ub2_vrs_policy.h"
#include <array>
#include <cassert>
#include <vector>
using namespace Vulkan::Ub2Vrs;
static std::vector<std::uint32_t> Fragment() {
    return {0x07230203, 0x00010000, 0, 2, 0, (5u<<16)|15u, 4, 1, 0x6e69616d, 0};
}
static FragmentClass With(std::initializer_list<std::uint32_t> instruction) {
    auto s = Fragment();
    s.insert(s.end(), instruction);
    return Classify(s);
}
int main() {
    assert(Classify(Fragment()) == FragmentClass::Color);
    assert(With({(4u<<16)|71u, 1, 11, 15}) == FragmentClass::Position);
    assert(With({(4u<<16)|71u, 1, 11, 22}) == FragmentClass::Sensitive);
    assert(With({(4u<<16)|71u, 1, 11, 20}) == FragmentClass::Sensitive);
    assert(With({(5u<<16)|72u, 1, 0, 11, 5014}) == FragmentClass::Sensitive);
    assert(With({(2u<<16)|17u, 35}) == FragmentClass::Sensitive);
    assert(With({(2u<<16)|17u, 68}) == FragmentClass::Sensitive);
    assert(With({(1u<<16)|252u}) == FragmentClass::Sensitive);
    assert(With({(1u<<16)|5380u}) == FragmentClass::Sensitive);
    assert(With({(1u<<16)|4416u}) == FragmentClass::Sensitive);
    assert(With({(1u<<16)|99u}) == FragmentClass::Sensitive);
    assert(With({0}) == FragmentClass::Unknown);
    assert(With({(3u<<16)|71u, 1}) == FragmentClass::Unknown);
    auto v = Fragment(); v[6] = 0; // vertex entry
    assert(Classify(v) == FragmentClass::Unknown);
    assert(!AllowsCoarse(FragmentClass::Position, false));
    assert(AllowsCoarse(FragmentClass::Position, true));
    assert(!AllowsCoarse(FragmentClass::Sensitive, true));
}
