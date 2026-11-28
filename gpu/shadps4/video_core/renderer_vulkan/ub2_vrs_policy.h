// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

#include <cstdint>
#include <span>

namespace Vulkan::Ub2Vrs {
// SPIR-V core encodings and registered extension enumerants from
// KhronosGroup/SPIRV-Headers, spirv/unified1/spirv.hpp11.
// Analyze the ACTUAL shader module, including disk-cached shaders and
// user SPIR-V patches. Unknown/malformed modules never qualify.
enum class FragmentClass : std::uint8_t { Unknown, Sensitive, Color, Position };
constexpr FragmentClass Classify(std::span<const std::uint32_t> words) {
    if (words.size() < 5 || words[0] != 0x07230203u) return FragmentClass::Unknown;
    bool fragment = false, position = false, sensitive = false;
    for (std::size_t i = 5; i < words.size();) {
        const auto count = words[i] >> 16;
        const auto op = words[i] & 0xffffu;
        if (!count || count > words.size() - i) return FragmentClass::Unknown;
        if (op == 15) { // OpEntryPoint
            if (count < 4) return FragmentClass::Unknown;
            if (words[i + 1] != 4) return FragmentClass::Unknown; // Fragment
            fragment = true;
        }
        if (op == 17) { // OpCapability
            if (count != 2) return FragmentClass::Unknown;
            const auto cap = words[i + 1];
            sensitive |= cap == 35 || (cap >= 61 && cap <= 68) ||
                cap == 4423 || cap == 4431 || cap == 5013 || cap == 5055 ||
                cap == 5297 || cap == 5347 || cap == 5363 || cap == 5372 ||
                cap == 5378 || cap == 5379;
        }
        if (op == 71 || op == 72) { // OpDecorate / OpMemberDecorate
            const std::uint32_t at = op == 71 ? 2 : 3;
            if (count <= at) return FragmentClass::Unknown;
            const auto decoration = words[i + at];
            sensitive |= decoration == 17; // Sample interpolation
            if (decoration == 11) { // BuiltIn
                if (count <= at + 1) return FragmentClass::Unknown;
                const auto b = words[i + at + 1];
                position |= b == 15; // FragCoord: optional coarse shading on opaque scene meshes
                sensitive |= (b >= 18 && b <= 20) || b == 22 || b == 23 ||
                    (b >= 36 && b <= 41) || (b >= 4416 && b <= 4420) ||
                    b == 4432 || b == 4444 || b == 4994 || b == 4997 || b == 5014;
            }
        }
        // Reject discard, sample-/subgroup-dependent behavior and side effects.
        sensitive |= op == 99 || (op >= 227 && op <= 242) || op == 252 ||
            op == 318 || op == 319 || (op >= 333 && op <= 366) ||
            op == 4416 || op == 4431 || op == 5056 || op == 5110 ||
            op == 5111 || op == 5296 || op == 5364 || op == 5365 ||
            op == 5380 || op == 5381 || op == 5614 || op == 5615 || op == 6035;
        i += count;
    }
    if (!fragment) return FragmentClass::Unknown;
    if (sensitive) return FragmentClass::Sensitive;
    return position ? FragmentClass::Position : FragmentClass::Color;
}

constexpr bool AllowsCoarse(FragmentClass type, bool allow_position) {
    return type == FragmentClass::Color || (allow_position && type == FragmentClass::Position);
}
} // namespace Vulkan::Ub2Vrs
