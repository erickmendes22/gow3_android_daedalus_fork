// SPDX-License-Identifier: GPL-2.0-or-later
// Optional Mali optimization: force early depth/stencil rejection only for
// side-effect-free opaque fragment SPIR-V. Works on already cached SPIR-V: it
// is applied when creating the VkShaderModule, not when serializing shaders.
#pragma once

#include <cstdint>
#include <span>
#include <unordered_map>
#include <utility>
#include <vector>
#include <spirv/unified1/spirv.h>

namespace Vulkan::MaliEarlyZ {

// Returns true only when an EarlyFragmentTests mode was safely inserted.
// A failure leaves the original program unchanged (output remains empty).
inline bool Transform(std::span<const uint32_t> words, std::vector<uint32_t>& output) {
    output.clear();
    if (words.size() < 5 || words[0] != SpvMagicNumber) return false;

    std::unordered_map<uint32_t, uint32_t> pointer_storage;
    std::unordered_map<uint32_t, uint32_t> value_storage;
    std::vector<uint32_t> stores;
    uint32_t fragment_entry = 0;
    size_t insert_at = 0;
    bool has_entrypoint = false;

    for (size_t i = 5; i < words.size();) {
        const uint32_t word = words[i], count = word >> 16, op = word & 0xffff;
        if (!count || i + count > words.size()) return false;
        const auto at_least = [&](size_t n) { return count >= n; };

        if (op == SpvOpEntryPoint) {
            if (!at_least(4) || has_entrypoint) return false;
            has_entrypoint = true;
            if (words[i + 1] != SpvExecutionModelFragment) return false;
            fragment_entry = words[i + 2];
            insert_at = i + count;
        } else if (op == SpvOpExecutionMode || op == SpvOpExecutionModeId) {
            if (!at_least(3)) return false;
            if (op == SpvOpExecutionMode &&
                (words[i + 2] == SpvExecutionModeEarlyFragmentTests ||
                 words[i + 2] == SpvExecutionModeDepthReplacing)) return false;
            insert_at = i + count;
        } else if (op == SpvOpDecorate) {
            if (!at_least(3)) return false;
            if (words[i + 2] == SpvDecorationBuiltIn && at_least(4) &&
                (words[i + 3] == SpvBuiltInFragDepth ||
                 words[i + 3] == SpvBuiltInSampleMask ||
                 words[i + 3] == SpvBuiltInFragStencilRefEXT))
                return false;
        } else if (op == SpvOpMemberDecorate) {
            if (!at_least(4)) return false;
            if (words[i + 3] == SpvDecorationBuiltIn && at_least(5) &&
                (words[i + 4] == SpvBuiltInFragDepth ||
                 words[i + 4] == SpvBuiltInSampleMask ||
                 words[i + 4] == SpvBuiltInFragStencilRefEXT)) return false;
        } else if (op == SpvOpTypePointer) {
            if (!at_least(4)) return false;
            pointer_storage[words[i + 1]] = words[i + 2];
        } else if (op == SpvOpStore) {
            if (!at_least(3)) return false;
            stores.push_back(words[i + 1]);
        } else if (op == SpvOpVariable || op == SpvOpAccessChain ||
                   op == SpvOpInBoundsAccessChain || op == SpvOpPtrAccessChain ||
                   op == SpvOpInBoundsPtrAccessChain || op == SpvOpCopyObject ||
                   op == SpvOpPhi || op == SpvOpSelect ||
                   op == SpvOpFunctionParameter || op == SpvOpLoad) {
            if (!at_least(3)) return false;
            if (const auto it = pointer_storage.find(words[i + 1]);
                it != pointer_storage.end()) {
                value_storage[words[i + 2]] = it->second;
            }
        }

        // Any observable shader write, side effect, discard, barrier, or
        // fragment-interlock operation must preserve the original shader.
        if (op == SpvOpKill || op == SpvOpTerminateInvocation ||
            op == SpvOpDemoteToHelperInvocationEXT ||
            op == SpvOpBeginInvocationInterlockEXT ||
            op == SpvOpEndInvocationInterlockEXT ||
            op == SpvOpImageWrite || op == SpvOpCopyMemory ||
            op == SpvOpCopyMemorySized || op == SpvOpControlBarrier ||
            op == SpvOpMemoryBarrier ||
            (op >= SpvOpAtomicLoad && op <= SpvOpAtomicXor) ||
            op == SpvOpAtomicFlagTestAndSet || op == SpvOpAtomicFlagClear ||
            op == SpvOpAtomicFAddEXT || op == SpvOpAtomicFMinEXT ||
            op == SpvOpAtomicFMaxEXT) return false;
        i += count;
    }
    if (!fragment_entry || !insert_at) return false;

    // Stores are allowed only to fragment outputs or shader-local scratch.
    // Writes to SSBOs, physical storage, workgroup memory, etc. are excluded.
    for (const uint32_t pointer : stores) {
        const auto it = value_storage.find(pointer);
        if (it == value_storage.end()) return false;
        if (it->second != SpvStorageClassOutput &&
            it->second != SpvStorageClassFunction &&
            it->second != SpvStorageClassPrivate) return false;
    }

    // SPIR-V logical layout: all entry points precede execution modes; insert
    // after their declarations, before debug/annotation/types/functions.
    output.assign(words.begin(), words.begin() + insert_at);
    output.push_back((3u << 16) | SpvOpExecutionMode);
    output.push_back(fragment_entry);
    output.push_back(SpvExecutionModeEarlyFragmentTests);
    output.insert(output.end(), words.begin() + insert_at, words.end());
    return true;
}

} // namespace Vulkan::MaliEarlyZ
