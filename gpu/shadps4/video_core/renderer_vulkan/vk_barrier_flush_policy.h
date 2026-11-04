// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

// A buffer dependency is independent of an image-layout transition. Keep
// tracking the first until an actual buffer hazard or a queue submission.
// This pure function is shared by Android/desktop and host unit tests.
namespace Vulkan {
struct BarrierFlushDecision {
    bool emit_memory;
    bool emit_images;
    bool retire_buffer_ranges;
    bool has_work() const { return emit_memory || emit_images; }
};

constexpr BarrierFlushDecision DecideBarrierFlush(bool split_image_and_buffer,
                                                  bool buffer_hazard, bool queue_submit,
                                                  bool pending_buffer_accesses,
                                                  bool pending_image_barriers) {
    const bool memory = pending_buffer_accesses &&
                        (!split_image_and_buffer || buffer_hazard || queue_submit);
    return {memory, pending_image_barriers, memory};
}
} // namespace Vulkan
