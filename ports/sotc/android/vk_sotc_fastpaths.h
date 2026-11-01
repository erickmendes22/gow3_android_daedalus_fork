// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
// SotC Android exact Vulkan recording-state memos.
//
// These caches do NOT cache guest resources, uploads, barriers, push constants,
// shader inputs or image contents. They may only avoid repeating two host Vulkan
// state-setting commands when a command buffer, tick, and rendering-state epoch
// are all identical. Every changed render pass invalidates the epoch.
#include <algorithm>
#include <cstdint>
#include <span>
#include <vector>

namespace SotcFastPath {

template<class CommandBuffer, class Pipeline>
class GraphicsPipelineMemo {
public:
    bool NeedsBind(CommandBuffer command, Pipeline pipeline,
                   std::uint64_t tick, std::uint64_t epoch) noexcept {
        const bool hit = valid && last_command == command && last_pipeline == pipeline &&
                         last_tick == tick && last_epoch == epoch;
        last_command = command;
        last_pipeline = pipeline;
        last_tick = tick;
        last_epoch = epoch;
        valid = true;
        return !hit;
    }
    void Invalidate() noexcept { valid = false; }
private:
    CommandBuffer last_command{};
    Pipeline last_pipeline{};
    std::uint64_t last_tick{}, last_epoch{};
    bool valid = false;
};

// Compare field values, not raw bytes: Vk*Description2EXT has possible padding.
// Each physical VkCmdSetVertexInputEXT reuses exactly the last complete state.
// First draw, render-pass change, submit tick, or changed attributes always emits.
template<class CommandBuffer, class Binding, class Attribute>
class VertexInputMemo {
    static bool SameBinding(const Binding& a, const Binding& b) {
        return a.binding == b.binding && a.stride == b.stride &&
               a.inputRate == b.inputRate && a.divisor == b.divisor;
    }
    static bool SameAttribute(const Attribute& a, const Attribute& b) {
        return a.location == b.location && a.binding == b.binding &&
               a.format == b.format && a.offset == b.offset;
    }
public:
    bool NeedsSet(CommandBuffer command, std::uint64_t tick, std::uint64_t epoch,
                  std::span<const Binding> bindings, std::span<const Attribute> attributes) {
        const bool hit = valid && last_command == command &&
                         last_tick == tick && last_epoch == epoch &&
                         std::ranges::equal(bindings, last_bindings, SameBinding) &&
                         std::ranges::equal(attributes, last_attributes, SameAttribute);
        if (hit) return false;
        last_command = command;
        last_tick = tick;
        last_epoch = epoch;
        last_bindings.assign(bindings.begin(), bindings.end());
        last_attributes.assign(attributes.begin(), attributes.end());
        valid = true;
        return true;
    }
    void Invalidate() noexcept { valid = false; }
private:
    CommandBuffer last_command{};
    std::uint64_t last_tick{}, last_epoch{};
    std::vector<Binding> last_bindings;
    std::vector<Attribute> last_attributes;
    bool valid = false;
};

} // namespace SotcFastPath
