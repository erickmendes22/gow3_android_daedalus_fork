// SPDX-FileCopyrightText: Copyright 2025 shadPS4 Emulator Project
// SPDX-License-Identifier: GPL-2.0-or-later

#include <thread>
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <unordered_map>
#ifndef _WIN32
#include <dlfcn.h>
#endif
#include <functional>

#include "gow3_copy.h"
#include "video_core/renderer_vulkan/vk_gpu_profiler.h"
#include "gow3_toggles.h"
#include "video_core/renderer_vulkan/vk_wait_diagnostics.h"
#include "video_core/renderer_vulkan/vk_mali_perf_stats.h"
#include "common/arch.h"
#include "common/assert.h"
#include "common/debug.h"
#include "common/thread.h"
#include "imgui/renderer/texture_manager.h"
#include "video_core/renderer_vulkan/vk_instance.h"
#include "video_core/renderer_vulkan/vk_scheduler.h"
#include "gow3_threads.h"

namespace Vulkan {

std::mutex Scheduler::submit_mutex;

Scheduler::Scheduler(const Instance& instance, bool threaded_recording)
    : instance{instance}, work_semaphore{instance}, command_pool{instance, &work_semaphore} {
    const char* unlocked_throttle = std::getenv("GOW3_MALI_UNLOCKED_SUBMIT_THROTTLE");
    mali_unlocked_submit_throttle =
        std::getenv("GOW3_ANDROID_PORT") &&
        instance.GetPhysicalDevice().getProperties().vendorID == 0x13B5 &&
        unlocked_throttle && unlocked_throttle[0] == '1';
    native_draw_batch_limit = instance.NativeDrawBatchLimit();
    const char* resource_cache = std::getenv("GOW3_MALI_GRAPHICS_RESOURCE_CACHE");
    graphics_resource_cache_enabled = std::getenv("GOW3_ANDROID_PORT") &&
        instance.GetPhysicalDevice().getProperties().vendorID == 0x13B5 &&
        (!resource_cache || resource_cache[0] != '0');
    // Per-renderer bind cache (never global across Vulkan command buffers).
    // GOW3_MALI_PIPELINE_BIND_CACHE=0 restores all legacy vkCmdBindPipeline calls.
    const char* bind_cache = std::getenv("GOW3_MALI_PIPELINE_BIND_CACHE");
    graphics_pipeline_bind_cache_enabled =
        std::getenv("GOW3_ANDROID_PORT") &&
        instance.GetPhysicalDevice().getProperties().vendorID == 0x13B5 &&
        (!bind_cache || bind_cache[0] != '0');
    // Only exact consecutive dynamic vertex-input state may be omitted.
    // The Vulkan state becomes unknown after every pipeline bind or raw
    // CommandBuffer() access, including post-processing and ImGui.
    const char* vertex_cache = std::getenv("GOW3_MALI_VERTEX_INPUT_CACHE");
    vertex_input_cache_enabled =
        std::getenv("GOW3_ANDROID_PORT") &&
        instance.GetPhysicalDevice().getProperties().vendorID == 0x13B5 &&
        (!vertex_cache || vertex_cache[0] != '0');
    const char* buffer_cache = std::getenv("GOW3_MALI_BUFFER_BIND_CACHE");
    buffer_bind_cache_enabled = vertex_input_cache_enabled &&
        (!buffer_cache || buffer_cache[0] != '0');
    // gow3: GOW3_VK_RECORD_THREAD=0 records on the calling thread.
    const char* env = std::getenv("GOW3_VK_RECORD_THREAD");
    if (threaded_recording && !(env && env[0] == '0')) {
        record_chunk = AcquireChunk();
        recorder_thread = std::jthread(std::bind_front(&Scheduler::RecorderThread, this));
        recording_threaded = true;
    }
#if TRACY_GPU_ENABLED
    profiler_scope = reinterpret_cast<tracy::VkCtxScope*>(std::malloc(sizeof(tracy::VkCtxScope)));
#endif
    AllocateWorkerCommandBuffers();
    priority_pending_ops_thread =
        std::jthread(std::bind_front(&Scheduler::PriorityPendingOpsThread, this));
}

Scheduler::~Scheduler() {
    if (recorder_thread.joinable()) {
        SyncRecording();
        recorder_thread.request_stop();
        recorder_cv.notify_all();
        recorder_thread.join();
    }
#if TRACY_GPU_ENABLED
    std::free(profiler_scope);
#endif
}

void Scheduler::BeginRendering(const RenderState& new_state) {
    RenderState effective_state = new_state;
#ifdef __ANDROID__
    // GoW3 may request attachment-less graphics passes with a 65535x65535
    // nominal render area (16-bit max). PanVK must size/track the tile region
    // even though the guest's dynamic scissors cover only a small rectangle.
    // A render area larger than the union of active scissors cannot produce
    // additional fragments. Keep attachment-backed passes completely intact.
    static const bool mali = std::getenv("GOW3_ANDROID_PORT") &&
        instance.GetPhysicalDevice().getProperties().vendorID == 0x13B5;
    const char* disable = std::getenv("GOW3_MALI_ATTACHMENTLESS_SCISSOR_AREA");
    if (mali && (!disable || disable[0] != '0') &&
        !new_state.depth_stencil_attachment.has_depth &&
        !new_state.depth_stencil_attachment.has_stencil) {
        bool has_color_attachment = false;
        for (u32 cb = 0; cb < new_state.num_color_attachments; ++cb) {
            has_color_attachment |= bool(new_state.color_attachments[cb].image_view);
        }
        if (!has_color_attachment && !dynamic_state.scissors.empty()) {
            u32 right = 1, bottom = 1;
            for (const auto& scissor : dynamic_state.scissors) {
                // Offscreen negative offsets are valid; saturate to the
                // positive framebuffer extent before narrowing to u16.
                const s64 x = s64(scissor.offset.x) + scissor.extent.width;
                const s64 y = s64(scissor.offset.y) + scissor.extent.height;
                right = std::max(right, u32(std::clamp<s64>(x, 1, new_state.width)));
                bottom = std::max(bottom, u32(std::clamp<s64>(y, 1, new_state.height)));
            }
            effective_state.width = u16(std::min<u32>(effective_state.width, right));
            effective_state.height = u16(std::min<u32>(effective_state.height, bottom));
        }
    }
#endif
#ifdef __ANDROID__
    // The old comparison includes clear values even for LOAD, and ends a pass
    // when the initial clear has been consumed. On tile GPUs this costs a
    // needless store/load of the exact same attachments. Never ignore an
    // incoming clear, a changed view/layout/extent, or an explicit EndRendering.
    static const bool merge_load = [] {
        const char* value = std::getenv("GOW3_MALI_MERGE_LOAD_PASSES");
        return !value || value[0] != '0';
    }();
    if (mali && merge_load && is_rendering) {
        auto previous = render_state;
        auto incoming = effective_state;
        // Ignore metadata of attachments absent in both states only.
        if (previous.num_color_attachments == incoming.num_color_attachments) {
            for (u32 i = incoming.num_color_attachments; i < incoming.color_attachments.size(); ++i)
                previous.color_attachments[i] = incoming.color_attachments[i] = RenderAttachment{};
        }
        for (u32 i = 0; i < incoming.num_color_attachments && i < previous.num_color_attachments; ++i) {
            if (!incoming.color_attachments[i].image_view && !previous.color_attachments[i].image_view)
                previous.color_attachments[i] = incoming.color_attachments[i] = RenderAttachment{};
        }
        if (!previous.depth_stencil_attachment.has_depth &&
            !previous.depth_stencil_attachment.has_stencil &&
            !incoming.depth_stencil_attachment.has_depth &&
            !incoming.depth_stencil_attachment.has_stencil)
            previous.depth_stencil_attachment = incoming.depth_stencil_attachment = RenderAttachment{};
        for (u32 i = 0; i < incoming.num_color_attachments && i < previous.num_color_attachments; ++i) {
            if (!incoming.color_attachments[i].is_clear) {
                previous.color_attachments[i].is_clear = 0;
                previous.color_attachments[i].clear_value = {};
                incoming.color_attachments[i].clear_value = {};
            }
        }
        auto& a = previous.depth_stencil_attachment;
        auto& b = incoming.depth_stencil_attachment;
        if (!b.depth_clear) { a.depth_clear = false; a.clear_value[0] = b.clear_value[0] = 0; }
        if (!b.stencil_clear) { a.stencil_clear = false; a.clear_value[1] = b.clear_value[1] = 0; }
        if (previous == incoming) {
            render_state = effective_state;
            return;
        }
    }
#endif
    // Include the effective area in render-state equality. If the scissor
    // grows on a later draw, end the earlier pass before expanding its area.
    if (is_rendering && render_state == effective_state) {
        return;
    }
    EndRendering();
    is_rendering = true;
    render_state = effective_state;

    std::array<vk::RenderingAttachmentInfo, 8> color_attachments;
    for (u32 i = 0; i < render_state.num_color_attachments; ++i) {
        const auto& cb = render_state.color_attachments[i];
        color_attachments[i] = vk::RenderingAttachmentInfo{
            .imageView = cb.image_view,
            .imageLayout = cb.image_layout,
            .loadOp = cb.is_clear ? vk::AttachmentLoadOp::eClear : vk::AttachmentLoadOp::eLoad,
            .storeOp = vk::AttachmentStoreOp::eStore,
            .clearValue = vk::ClearValue{.color = vk::ClearColorValue{.uint32 = cb.clear_value}},
        };
    }

    const auto& db = render_state.depth_stencil_attachment;
    const vk::RenderingAttachmentInfo depth_attachment = {
        .imageView = db.image_view,
        .imageLayout = db.image_layout,
        .loadOp = db.depth_clear ? vk::AttachmentLoadOp::eClear : vk::AttachmentLoadOp::eLoad,
        .storeOp = vk::AttachmentStoreOp::eStore,
        .clearValue =
            vk::ClearValue{.depthStencil = vk::ClearDepthStencilValue{.depth = std::bit_cast<float>(
                                                                          db.clear_value[0])}},
    };
    const vk::RenderingAttachmentInfo stencil_attachment = {
        .imageView = db.image_view,
        .imageLayout = db.image_layout,
        .loadOp = db.stencil_clear ? vk::AttachmentLoadOp::eClear : vk::AttachmentLoadOp::eLoad,
        .storeOp = vk::AttachmentStoreOp::eStore,
        .clearValue = vk::ClearValue{.depthStencil =
                                         vk::ClearDepthStencilValue{.stencil = db.clear_value[1]}},
    };

    const vk::RenderingInfo rendering_info = {
        .renderArea =
            {
                .offset = {0, 0},
                .extent = {render_state.width, render_state.height},
            },
        .layerCount = render_state.num_layers,
        .colorAttachmentCount = render_state.num_color_attachments,
        .pColorAttachments = color_attachments.data(),
        .pDepthAttachment = db.has_depth ? &depth_attachment : nullptr,
        .pStencilAttachment = db.has_stencil ? &stencil_attachment : nullptr,
    };

    if (!recording_threaded) {
        FlushNativeDrawBatch(current_cmdbuf);
        last_graphics_resource_layout = vk::PipelineLayout{};
        current_cmdbuf.beginRendering(rendering_info);
        return;
    }
    // The attachment infos live on this stack frame: the recorded closure keeps copies.
    RecordGraphicsOrdered([info = rendering_info, color_attachments, depth_attachment,
            stencil_attachment](vk::CommandBuffer cmdbuf) mutable {
        info.pColorAttachments = color_attachments.data();
        if (info.pDepthAttachment) {
            info.pDepthAttachment = &depth_attachment;
        }
        if (info.pStencilAttachment) {
            info.pStencilAttachment = &stencil_attachment;
        }
        cmdbuf.beginRendering(info);
    });
}

void Scheduler::EndRendering() {
    if (!is_rendering) {
        return;
    }
    is_rendering = false;
    RecordGraphicsOrdered([this](vk::CommandBuffer cmdbuf) {
        cmdbuf.endRendering();
        // Auxiliary render/transfer commands between passes may bind their own buffers.
        last_vertex_buffer_cmd = last_index_buffer_cmd = vk::CommandBuffer{};
    });
}

void Scheduler::TraceDirectRecording(void* caller) {
    static const bool enabled = [] {
        const char* env = std::getenv("GOW3_RECORDER_TRACE");
        return env && env[0] == '1';
    }();
    if (!enabled) {
        return;
    }
    static std::mutex mutex;
    static std::unordered_map<void*, u64> callers;
    static u64 calls;
    std::scoped_lock lk{mutex};
    ++callers[caller];
    if (++calls % 2000) {
        return;
    }
    std::vector<std::pair<u64, void*>> top;
    for (const auto& [address, count] : callers) {
        top.emplace_back(count, address);
    }
    std::ranges::sort(top, std::greater{});
    for (size_t i = 0; i < std::min<size_t>(top.size(), 8); ++i) {
#ifdef _WIN32
        struct { const char* dli_fname; void* dli_fbase; } info{nullptr, nullptr};
#else
        Dl_info info{};
        dladdr(top[i].second, &info);
#endif
        std::printf("Recorder sync caller: %llu x %s+0x%lx\n",
                    static_cast<unsigned long long>(top[i].first),
                    info.dli_fname ? info.dli_fname : "?",
                    static_cast<unsigned long>(reinterpret_cast<uintptr_t>(top[i].second) -
                                               reinterpret_cast<uintptr_t>(info.dli_fbase)));
    }
    callers.clear();
}

std::unique_ptr<RecordChunk> Scheduler::AcquireChunk() {
    std::scoped_lock lk{recorder_mutex};
    if (free_chunks.empty()) {
        return std::make_unique<RecordChunk>();
    }
    auto chunk = std::move(free_chunks.back());
    free_chunks.pop_back();
    return chunk;
}

void Scheduler::SignalAfterHostCopies(std::function<void()> signal) {
    if (!IsRecordingDeferred()) {
        WaitHostCopies();
        signal();
        return;
    }
    Gow3Copy::FlushBatch();
    deferred_signals_issued.fetch_add(1, std::memory_order_relaxed);
    Record([signal = std::move(signal), done = deferred_signals_done](vk::CommandBuffer) mutable {
        Gow3Copy::AfterCopies([signal = std::move(signal), done = std::move(done)] {
            signal();
            done->fetch_add(1, std::memory_order_release);
        });
    });
    KickRecording(true);
}

void Scheduler::WaitDeferredSignals() {
    const u64 issued = deferred_signals_issued.load(std::memory_order_relaxed);
    if (deferred_signals_done->load(std::memory_order_acquire) >= issued ||
        Gow3Toggle::Disabled(Gow3Toggle::OrderedGuestWrites)) {
        return;
    }
    Gow3Stats::WaitTimer timer{Gow3Stats::host_copies_wait_ns};
    KickRecording(true);
    while (deferred_signals_done->load(std::memory_order_acquire) < issued) {
        // Helps the copy threads the signals wait for.
        Gow3Copy::WaitAsync();
        std::this_thread::yield();
    }
}

void Scheduler::WaitHostCopies() {
    if (host_copies_done.load(std::memory_order_acquire) < host_copies_issued) {
        Gow3Stats::WaitTimer timer{Gow3Stats::host_copies_wait_ns};
        Gow3Stats::host_copy_waits.fetch_add(1, std::memory_order_relaxed);
        KickRecording(true);
        while (host_copies_done.load(std::memory_order_acquire) < host_copies_issued) {
            std::this_thread::yield();
        }
    }
    Gow3Stats::WaitTimer timer{Gow3Stats::copy_threads_wait_ns};
    Gow3Copy::WaitAsync();
}

void Scheduler::KickRecording(bool force) {
    if (!recording_threaded) {
        return;
    }
    std::scoped_lock kick_lock{kick_mutex};
    // Callers kick where nobody holds the raw command buffer: deferral resumes.
    direct_mode = false;
    // Batches of tens of KiB keep the queue handoff cheap relative to the work it carries.
    if (!force && full_chunks.empty() && CurrentChunk().Size() < 32 * 1024) {
        return;
    }
    if (full_chunks.empty() && CurrentChunk().Empty()) {
        return;
    }
    // Acquire the replacement before handing over the current chunk. This mirrors Bloodborne's
    // issue #100 fix: record_chunk remains valid throughout the handover, including if another
    // recording path is entered while the queue lock is held.
    std::unique_ptr<RecordChunk> next_record =
        CurrentChunk().Empty() ? nullptr : AcquireChunk();
    bool wake;
    {
        std::scoped_lock lk{recorder_mutex};
        for (auto& chunk : full_chunks) {
            recorder_queue.push_back(std::move(chunk));
        }
        if (next_record) {
            record_chunk.swap(next_record);
            recorder_queue.push_back(std::move(next_record));
        }
        wake = recorder_sleeping;
        queued_chunks.store(recorder_queue.size(), std::memory_order_release);
    }
    full_chunks.clear();
    // A busy recorder picks the new chunks up by itself: waking it is a syscall per draw.
    if (wake) {
        recorder_cv.notify_one();
    }
}

void Scheduler::SyncRecording() {
    if (!recording_threaded) {
        return;
    }
    KickRecording(true);
    Gow3Stats::WaitTimer timer{Gow3Stats::sync_recording_ns};
    std::unique_lock lk{recorder_mutex};
    recorder_idle_cv.wait(lk, [this] { return recorder_queue.empty() && !recorder_busy; });
}

void Scheduler::RecorderThread(std::stop_token stoken) {
    Common::SetCurrentThreadName("gow3:VkRecorder");
    while (true) {
        // Spin briefly before sleeping: the next chunk usually follows within microseconds,
        // and a sleeping recorder costs the GPU thread a wake-up syscall per kick. With few
        // hardware threads (Steam Deck: 8) the spin would take time from guest threads.
        static const auto spin_time = std::chrono::microseconds(
            Gow3Threads::Available() >= 12 ? 200 : 20);
        const auto spin_until = std::chrono::steady_clock::now() + spin_time;
        for (u32 spins = 1; queued_chunks.load(std::memory_order_acquire) == 0; ++spins) {
            COMMON_CPU_RELAX();
            // The clock is read every 256 pauses, not per iteration.
            if (!(spins & 255) &&
                (stoken.stop_requested() || std::chrono::steady_clock::now() >= spin_until)) {
                break;
            }
        }
        std::unique_ptr<RecordChunk> chunk;
        {
            std::unique_lock lk{recorder_mutex};
            recorder_sleeping = true;
            recorder_cv.wait(lk, stoken, [this] { return !recorder_queue.empty(); });
            recorder_sleeping = false;
            if (recorder_queue.empty()) {
                return; // stop requested
            }
            chunk = std::move(recorder_queue.front());
            recorder_queue.pop_front();
            queued_chunks.store(recorder_queue.size(), std::memory_order_release);
            recorder_busy = true;
        }
        // current_cmdbuf only changes after SyncRecording(), which waits for this thread.
        chunk->Execute(current_cmdbuf);
        FlushNativeDrawBatch(current_cmdbuf);
        {
            std::scoped_lock lk{recorder_mutex};
            free_chunks.push_back(std::move(chunk));
            recorder_busy = false;
            if (recorder_queue.empty()) {
                recorder_idle_cv.notify_all();
            }
        }
    }
}

void Scheduler::Flush(SubmitInfo& info) {
    // When flushing, we only send data to the driver; no waiting is necessary.
    SubmitExecution(info);
}

void Scheduler::Flush() {
    SubmitInfo info{};
    Flush(info);
}

void Scheduler::Finish(std::source_location caller) {
    // When finishing, we need to wait for the submission to have executed on the device.
    const u64 presubmit_tick = CurrentTick();
    const bool diagnose = WaitDiagnostics::TickProfileEnabled();
    const auto start = diagnose ? std::chrono::steady_clock::now() : std::chrono::steady_clock::time_point{};
    SubmitInfo info{};
    SubmitExecution(info);
    const u64 submit_ns = diagnose ? std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now() - start).count() : 0;
    Wait(presubmit_tick, caller, submit_ns);
}

void Scheduler::WaitSubmitted(std::source_location caller) {
    const u64 tick = CurrentTick();
    if (tick > 1) {
        Wait(tick - 1, caller);
    }
}

void Scheduler::Wait(u64 tick, std::source_location caller, u64 submit_ns) {
    if (work_semaphore.IsFree(tick)) return;
    const bool diagnose = WaitDiagnostics::TickProfileEnabled();
    auto start = diagnose ? std::chrono::steady_clock::now() : std::chrono::steady_clock::time_point{};
    ASSERT_MSG(tick <= work_semaphore.CurrentTick(), "Wait for unreserved scheduler tick");
    if (tick >= work_semaphore.CurrentTick()) {
        // Make sure we are not waiting for the current tick without signalling
        SubmitInfo info{};
        Flush(info);
    }
    Gow3Stats::WaitTimer timer{Gow3Stats::tick_wait_ns};
    const auto submitted = diagnose ? std::chrono::steady_clock::now() : start;
    work_semaphore.Wait(tick, caller);
    if (diagnose) {
        const auto completed = std::chrono::steady_clock::now();
        WaitDiagnostics::Get().Add(caller.file_name(), caller.line(),
            submit_ns + std::chrono::duration_cast<std::chrono::nanoseconds>(submitted - start).count(),
            std::chrono::duration_cast<std::chrono::nanoseconds>(completed - submitted).count());
    }
}

void Scheduler::PopPendingOperations() {
    if (num_pending_ops.load(std::memory_order_acquire) == 0) {
        return; // every draw comes here
    }
    std::unique_lock lk(pending_ops_mutex);
    // gow3: this runs on every draw and dispatch. Querying the timeline semaphore is an
    // ioctl, so it is skipped when nothing waits and done once per 32 calls (~0.3 ms; reading
    // the clock per draw instead was itself a hot spot).
    if (pending_ops.empty()) {
        return;
    }
    if (!work_semaphore.IsFree(pending_ops.front().gpu_tick)) {
        // Bachata ARM64 reclaims resources using confirmed GPU ticks, without
        // querying the Vulkan timeline from the draw hot path. Mali already
        // uses bounded submissions, whose mandatory waits advance cached ticks.
        // =0 explicitly restores the original 1-in-32-draw polling path.
        static const bool mali_cached_pending_ticks = [this] {
#ifdef __ANDROID__
            const char* selected = std::getenv("GOW3_MALI_CACHED_PENDING_TICKS");
            const char* legacy_submit = std::getenv("GOW3_VK_POLL_EACH_SUBMIT");
            return std::getenv("GOW3_ANDROID_PORT") != nullptr &&
                   instance.GetPhysicalDevice().getProperties().vendorID == 0x13B5 &&
                   (!selected || selected[0] != '0') &&
                   !(legacy_submit && legacy_submit[0] == '1');
#else
            return false;
#endif
        }();
        if (mali_cached_pending_ticks) {
            // Leave this object pending; only a confirmed completed tick
            // may retire it, as on the original Bachata scheduler.
            return;
        }
        if ((++pending_polls & 31) != 0 && !Gow3Toggle::Disabled(Gow3Toggle::PendingPollLimit)) {
            return;
        }
        const bool sample_poll = MaliPerfStats::Enabled();
        const auto query_start = sample_poll ? MaliPerfStats::Clock::now()
                                              : MaliPerfStats::TimePoint{};
        work_semaphore.Refresh();
        if (sample_poll)
            MaliPerfStats::Record(MaliPerfStats::Stage::PendingTimelineQuery, query_start);
    }
    while (!pending_ops.empty() && work_semaphore.IsFree(pending_ops.front().gpu_tick)) {
        pending_ops.front().callback();
        pending_ops.pop();
        num_pending_ops.fetch_sub(1, std::memory_order_release);
    }
}

void Scheduler::SetVertexInputCached(
    vk::CommandBuffer cmdbuf,
    std::span<const vk::VertexInputBindingDescription2EXT> bindings,
    std::span<const vk::VertexInputAttributeDescription2EXT> attributes) {
    // Compare named fields, not padding bytes. The cache is owned by this
    // scheduler and accessed by the active Vulkan recorder in command order.
    const auto same_bindings = [&] {
        return last_vertex_input_bindings.size() == bindings.size() &&
            std::equal(bindings.begin(), bindings.end(), last_vertex_input_bindings.begin(),
                       [](const auto& a, const auto& b) {
                           // Extension pNext payloads may affect interpretation.
                           // Cache only the standard null-pNext representation.
                           return !a.pNext && !b.pNext && a.sType == b.sType &&
                                  a.binding == b.binding && a.stride == b.stride &&
                                  a.inputRate == b.inputRate && a.divisor == b.divisor;
                       });
    };
    const auto same_attributes = [&] {
        return last_vertex_input_attributes.size() == attributes.size() &&
            std::equal(attributes.begin(), attributes.end(), last_vertex_input_attributes.begin(),
                       [](const auto& a, const auto& b) {
                           return !a.pNext && !b.pNext && a.sType == b.sType &&
                                  a.location == b.location && a.binding == b.binding &&
                                  a.format == b.format && a.offset == b.offset;
                       });
    };
    if (vertex_input_cache_enabled && cmdbuf == last_vertex_input_cmd &&
        same_bindings() && same_attributes()) {
        MaliPerfStats::CountVertexInputSet(true);
        return;
    }
    FlushNativeDrawBatch(cmdbuf);
    cmdbuf.setVertexInputEXT(bindings, attributes);
    if (!last_vertex_buffer_dynamic) last_vertex_buffer_cmd = vk::CommandBuffer{};
    if (vertex_input_cache_enabled) {
        last_vertex_input_bindings.assign(bindings.begin(), bindings.end());
        last_vertex_input_attributes.assign(attributes.begin(), attributes.end());
        last_vertex_input_cmd = cmdbuf;
    }
    MaliPerfStats::CountVertexInputSet(false);
}

void Scheduler::BindVertexBuffersCached(vk::CommandBuffer cmdbuf, bool dynamic_input,
                                       std::span<const vk::Buffer> buffers,
                                       std::span<const vk::DeviceSize> offsets,
                                       std::span<const vk::DeviceSize> sizes,
                                       std::span<const vk::DeviceSize> strides) {
    if (buffers.empty()) return;
    const auto same = [](auto incoming, const auto& previous) {
        return incoming.size() == previous.size() &&
               std::equal(incoming.begin(), incoming.end(), previous.begin());
    };
    if (buffer_bind_cache_enabled && cmdbuf == last_vertex_buffer_cmd &&
        dynamic_input == last_vertex_buffer_dynamic && same(buffers, last_vertex_buffers) &&
        same(offsets, last_vertex_offsets) && same(sizes, last_vertex_sizes) &&
        same(strides, last_vertex_strides)) {
        MaliPerfStats::CountVertexBufferBind(true);
        return;
    }
    FlushNativeDrawBatch(cmdbuf);
    const u32 count = static_cast<u32>(buffers.size());
    u32 first = 0, end = count;
    if (buffer_bind_cache_enabled && cmdbuf == last_vertex_buffer_cmd &&
        dynamic_input && last_vertex_buffer_dynamic &&
        last_vertex_buffers.size() == count && last_vertex_offsets.size() == count) {
        const auto unchanged = [&](u32 i) {
            return buffers[i] == last_vertex_buffers[i] && offsets[i] == last_vertex_offsets[i];
        };
        while (first < end && unchanged(first)) ++first;
        while (end > first && unchanged(end - 1)) --end;
    }
    if (dynamic_input) {
        if (end > first) cmdbuf.bindVertexBuffers(first, end - first,
                                                 buffers.data() + first, offsets.data() + first);
    } else {
        cmdbuf.bindVertexBuffers2(0, count, buffers.data(), offsets.data(),
                                 sizes.data(), strides.data());
    }
    if (buffer_bind_cache_enabled) {
        last_vertex_buffers.assign(buffers.begin(), buffers.end());
        last_vertex_offsets.assign(offsets.begin(), offsets.end());
        last_vertex_sizes.assign(sizes.begin(), sizes.end());
        last_vertex_strides.assign(strides.begin(), strides.end());
        last_vertex_buffer_dynamic = dynamic_input;
        last_vertex_buffer_cmd = cmdbuf;
    }
    MaliPerfStats::CountVertexBufferBind(false);
}

void Scheduler::BindIndexBufferCached(vk::CommandBuffer cmdbuf, vk::Buffer buffer,
                                     vk::DeviceSize offset, vk::IndexType type) {
    if (buffer_bind_cache_enabled && cmdbuf == last_index_buffer_cmd &&
        buffer == last_index_buffer && offset == last_index_offset && type == last_index_type) {
        MaliPerfStats::CountIndexBufferBind(true);
        return;
    }
    FlushNativeDrawBatch(cmdbuf);
    cmdbuf.bindIndexBuffer(buffer, offset, type);
    if (buffer_bind_cache_enabled) {
        last_index_buffer_cmd = cmdbuf;
        last_index_buffer = buffer;
        last_index_offset = offset;
        last_index_type = type;
    }
    MaliPerfStats::CountIndexBufferBind(false);
}

void Scheduler::BindGraphicsPipelineCached(vk::CommandBuffer cmdbuf, vk::Pipeline pipeline) {
    const bool same = graphics_pipeline_bind_cache_enabled &&
        cmdbuf == last_graphics_bind_cmd && pipeline == last_graphics_bind_pipeline;
    if (same) {
        MaliPerfStats::CountGraphicsPipelineBind(true);
        return;
    }
    FlushNativeDrawBatch(cmdbuf);
    cmdbuf.bindPipeline(vk::PipelineBindPoint::eGraphics, pipeline);
    // Conservatively invalidate dynamic vertex input whenever a graphics
    // pipeline changes. Some pipelines may use static vertex input; Vulkan
    // commands recorded before binding must not be assumed to survive it.
    last_vertex_input_cmd = vk::CommandBuffer{};
    // Dynamic vertex buffer handles/offsets survive a graphics pipeline bind.
    // Static/stride-aware bindings retain the conservative invalidation.
    if (!last_vertex_buffer_dynamic) last_vertex_buffer_cmd = vk::CommandBuffer{};
    // A graphics pipeline bind does not alter the bound index VkBuffer.
    // Raw commands, rendering scope ends and command buffer resets still
    // invalidate the index cache before reuse.
    if (graphics_pipeline_bind_cache_enabled) {
        last_graphics_bind_cmd = cmdbuf;
        last_graphics_bind_pipeline = pipeline;
    }
    MaliPerfStats::CountGraphicsPipelineBind(false);
}

void Scheduler::TraceWork(u64 kind, u64 a, u64 b, u64 c) {
    if (!work_semaphore.TraceEnabled()) return;
    auto& rec = submit_history;
    const u64 seq = rec.item_count++;
    const Semaphore::WorkItem item{kind, a, b, c};
    rec.items[seq % rec.items.size()] = item;
    if (kind < rec.categories.size()) {
        auto& summary = rec.categories[kind];
        if (!summary.count++) {
            summary.first = item;
            summary.first_seq = seq;
        }
        summary.last = item;
        summary.last_seq = seq;
        summary.signature = (summary.signature ^ a ^ (b * 0x9e3779b97f4a7c15ULL) ^
                             (c * 0xbf58476d1ce4e5b9ULL)) * 0x100000001b3ULL;
    }
    if (kind == 1) ++rec.draw_count;
    else if (kind == 2) rec.upload_bytes += c;
    else if (kind == 3) rec.download_bytes += c;
}

void Scheduler::FlushNativeDrawBatch(vk::CommandBuffer cmdbuf) {
    if (!native_draw_count) return;
    const u32 n = native_draw_count;
    native_draw_count = 0;
    if (n == 1) {
        if (native_indexed) {
            const auto& a = native_indexed_draws[0];
            cmdbuf.drawIndexed(a.indexCount, native_instances, a.firstIndex,
                               a.vertexOffset, native_first_instance);
        } else {
            const auto& a = native_draws[0];
            cmdbuf.draw(a.vertexCount, native_instances, a.firstVertex, native_first_instance);
        }
    } else {
        const auto& dispatch = VULKAN_HPP_DEFAULT_DISPATCHER;
        if (native_indexed)
            dispatch.vkCmdDrawMultiIndexedEXT(static_cast<VkCommandBuffer>(cmdbuf), n,
                native_indexed_draws.data(), native_instances, native_first_instance,
                sizeof(VkMultiDrawIndexedInfoEXT), nullptr);
        else
            dispatch.vkCmdDrawMultiEXT(static_cast<VkCommandBuffer>(cmdbuf), n,
                native_draws.data(), native_instances, native_first_instance,
                sizeof(VkMultiDrawInfoEXT));
        TraceWork(9, n, native_indexed, native_instances);
        native_draws_saved += n - 1;
        ++native_batches;
        if (native_batches <= 4 || (native_batches & 4095u) == 0)
            std::printf("GOW3_MALI_NATIVE_DRAW_BATCH batches=%llu saved_commands=%llu last=%u\n",
                static_cast<unsigned long long>(native_batches),
                static_cast<unsigned long long>(native_draws_saved), n);
    }
    MaliPerfStats::CountDrawRecorded(1);
}

void Scheduler::QueueNativeDraw(vk::CommandBuffer cmdbuf, bool indexed, u32 count,
                               u32 instances, u32 first_index, s32 first_vertex,
                               u32 first_instance) {
    ASSERT(NativeDrawBatchEnabled());
    if (native_draw_count &&
        (native_indexed != indexed || native_instances != instances ||
         native_first_instance != first_instance ||
         native_draw_count >= native_draw_batch_limit))
        FlushNativeDrawBatch(cmdbuf);
    native_indexed = indexed;
    native_instances = instances;
    native_first_instance = first_instance;
    if (indexed)
        native_indexed_draws[native_draw_count] = {first_index, count, first_vertex};
    else
        native_draws[native_draw_count] = {static_cast<u32>(first_vertex), count};
    ++native_draw_count;
}

void Scheduler::BindGraphicsResourcesCached(vk::CommandBuffer cmdbuf,
    vk::PipelineLayout layout, vk::ShaderStageFlags stages,
    std::span<const vk::WriteDescriptorSet> writes, const void* push_data, size_t push_size) {
    auto& key = graphics_resource_scratch;
    key.clear();
    const auto append = [&](const void* data, size_t size) {
        if (!size) return;
        const size_t old = key.size();
        key.resize(old + size);
        std::memcpy(key.data() + old, data, size);
    };
    bool cacheable = GraphicsResourceCacheEnabled() || NativeDrawBatchEnabled();
    const auto* push_bytes = static_cast<const u8*>(push_data);
    const auto write_count = writes.size();
    append(&write_count, sizeof(write_count));
    for (const auto& w : writes) {
        if (w.pNext) { cacheable = false; break; }
        append(&w.dstBinding, sizeof(w.dstBinding));
        append(&w.dstArrayElement, sizeof(w.dstArrayElement));
        append(&w.descriptorCount, sizeof(w.descriptorCount));
        append(&w.descriptorType, sizeof(w.descriptorType));
        switch (w.descriptorType) {
        case vk::DescriptorType::eUniformBuffer:
        case vk::DescriptorType::eStorageBuffer:
            if (!w.pBufferInfo) { cacheable = false; break; }
            for (u32 i = 0; i < w.descriptorCount; ++i) {
                const auto& info = w.pBufferInfo[i];
                append(&info.buffer, sizeof(info.buffer));
                append(&info.offset, sizeof(info.offset));
                append(&info.range, sizeof(info.range));
            }
            break;
        case vk::DescriptorType::eSampler:
        case vk::DescriptorType::eCombinedImageSampler:
        case vk::DescriptorType::eSampledImage:
        case vk::DescriptorType::eStorageImage:
            if (!w.pImageInfo) { cacheable = false; break; }
            for (u32 i = 0; i < w.descriptorCount; ++i) {
                const auto& info = w.pImageInfo[i];
                if (w.descriptorType == vk::DescriptorType::eSampler ||
                    w.descriptorType == vk::DescriptorType::eCombinedImageSampler)
                    append(&info.sampler, sizeof(info.sampler));
                if (w.descriptorType != vk::DescriptorType::eSampler) {
                    append(&info.imageView, sizeof(info.imageView));
                    append(&info.imageLayout, sizeof(info.imageLayout));
                }
            }
            break;
        case vk::DescriptorType::eUniformTexelBuffer:
        case vk::DescriptorType::eStorageTexelBuffer:
            if (!w.pTexelBufferView) { cacheable = false; break; }
            append(w.pTexelBufferView, w.descriptorCount * sizeof(vk::BufferView));
            break;
        default: cacheable = false; break;
        }
        if (!cacheable) break;
    }
    const bool same_layout = cacheable && last_graphics_resource_layout == layout &&
                             last_graphics_resource_stages == stages;
    const bool same_push = same_layout && last_graphics_push_key.size() == push_size &&
                           std::equal(last_graphics_push_key.begin(), last_graphics_push_key.end(), push_bytes);
    const bool same_descriptors = same_layout && last_graphics_resource_key == key;
    graphics_push_skips += same_push;
    graphics_descriptor_skips += same_descriptors;
    if ((++graphics_state_calls & 65535u) == 0)
        std::printf("GOW3_MALI_GRAPHICS_STATE calls=%llu push_skips=%llu descriptor_skips=%llu\n",
            (unsigned long long)graphics_state_calls, (unsigned long long)graphics_push_skips,
            (unsigned long long)graphics_descriptor_skips);
    if (same_push && same_descriptors) return;
    FlushNativeDrawBatch(cmdbuf);
    if (!same_push) cmdbuf.pushConstants(layout, stages, 0u, static_cast<u32>(push_size), push_data);
    if (!same_descriptors && !writes.empty())
        cmdbuf.pushDescriptorSetKHR(vk::PipelineBindPoint::eGraphics, layout, 0, writes);
    last_graphics_resource_layout = cacheable ? layout : vk::PipelineLayout{};
    last_graphics_resource_stages = stages;
    if (cacheable) {
        if (!same_descriptors) last_graphics_resource_key.swap(key);
        if (!same_push) last_graphics_push_key.assign(push_bytes, push_bytes + push_size);
    }
}

void Scheduler::AllocateWorkerCommandBuffers() {
    const vk::CommandBufferBeginInfo begin_info = {
        .flags = vk::CommandBufferUsageFlagBits::eOneTimeSubmit,
    };

    ASSERT(native_draw_count == 0);
    current_cmdbuf = command_pool.Commit();
    last_graphics_resource_layout = vk::PipelineLayout{};
    last_graphics_bind_cmd = vk::CommandBuffer{};
    last_graphics_bind_pipeline = vk::Pipeline{};
    last_vertex_input_cmd = vk::CommandBuffer{};
    last_vertex_buffer_cmd = last_index_buffer_cmd = vk::CommandBuffer{};
    Check(current_cmdbuf.begin(begin_info));

    // Invalidate dynamic state so it gets applied to the new command buffer.
    dynamic_state.Invalidate();

#if TRACY_GPU_ENABLED
    auto* profiler_ctx = instance.GetProfilerContext();
    if (profiler_ctx) {
        static const auto scope_loc =
            GPU_SCOPE_LOCATION("Guest Frame", MarkersPalette::GpuMarkerColor);
        new (profiler_scope) tracy::VkCtxScope{profiler_ctx, &scope_loc, current_cmdbuf, true};
    }
#endif
}

void Scheduler::SubmitExecution(SubmitInfo& info) {
    // Compare Bachata's deeper timeline queue with GoW3's old PanVK cap=2.
    // Only one out of 32 lock/record/submit operations are timed.
    const bool mali_submit_sample = MaliPerfStats::SampleSubmit();
    std::unique_lock order{mali_submission_order_mutex, std::defer_lock};
    if (mali_unlocked_submit_throttle) order.lock();
    const auto lock_start = mali_submit_sample ? MaliPerfStats::Clock::now()
                                               : MaliPerfStats::TimePoint{};
    std::unique_lock lk{submit_mutex};
    if (mali_submit_sample)
        MaliPerfStats::Record(MaliPerfStats::Stage::SubmitMutex, lock_start);
    // Do not advertise a new logical tick while this scheduler is merely
    // waiting for queue capacity. The per-scheduler lock holds the reservation
    // stable if the global queue mutex is released below.
    const u64 signal_value = mali_unlocked_submit_throttle
        ? work_semaphore.CurrentTick() : work_semaphore.NextTick();

    // BACHATA ARM64's bounded timeline policy: do not issue
    // vkGetSemaphoreCounterValue on every submit (a costly Turnip ioctl).
    // Instead, at most eight submissions remain in flight. We block on an
    // exact, already submitted GPU tick only if the producer outruns the GPU.
    // Readback demand paths retain their own mandatory waits; no guest memory
    // becomes visible until its matching timeline tick is complete.
    // PanVK's experimental Mali path needs a shallower GPU queue to avoid
    // building up driver allocations and unbounded outstanding work.
    // Default is unchanged for Adreno/desktop.
    static const u64 MaxAndroidInFlightSubmissions = [] {
        const char* value = std::getenv("GOW3_VK_MAX_IN_FLIGHT");
        if (value && *value) {
            const u64 requested = std::strtoull(value, nullptr, 10);
            if (requested >= 1 && requested <= 8) {
                return requested;
            }
        }
        return u64{8};
    }();
    // Cache the policy once: this is the hot path for thousands of submissions.
    // GOW3_VK_POLL_EACH_SUBMIT=1 re-enables the old path for device A/B testing.
    static const bool bounded_submit = [] {
        const char* opt_out = std::getenv("GOW3_VK_POLL_EACH_SUBMIT");
        return std::getenv("GOW3_ANDROID_PORT") != nullptr &&
               !(opt_out && opt_out[0] == '1');
    }();
    const auto wait_for_capacity = [&] {
    if (bounded_submit && signal_value > MaxAndroidInFlightSubmissions) {
        // Every forced wait is measured: this is precisely the suspected
        // 60->5 FPS menu bottleneck, unlike AHB copy timing. The readback,
        // guest-memory and presentation fences remain intact.
        const bool mali_timing = MaliPerfStats::Enabled();
        const auto throttle_start = mali_timing ? MaliPerfStats::Clock::now()
                                                : MaliPerfStats::TimePoint{};
        const bool profile = WaitDiagnostics::TickProfileEnabled();
        const auto wait_start = profile ? std::chrono::steady_clock::now()
                                        : std::chrono::steady_clock::time_point{};
        if (mali_unlocked_submit_throttle) lk.unlock();
        {
            // This cost was absent from Frame stats: GPU ticks in R5 even
            // when submit_throttle measured more than five seconds/window.
            Gow3Stats::WaitTimer timer{Gow3Stats::tick_wait_ns};
            work_semaphore.Wait(signal_value - MaxAndroidInFlightSubmissions);
        }
        if (profile) {
            const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(
                std::chrono::steady_clock::now() - wait_start).count();
            WaitDiagnostics::Get().Add("submit_throttle", 0, 0, elapsed);
        }
        if (mali_timing)
            MaliPerfStats::Record(MaliPerfStats::Stage::SubmitThrottle, throttle_start);
        if (mali_unlocked_submit_throttle) lk.lock();
    }
    };
    if (!mali_unlocked_submit_throttle) wait_for_capacity();

#if TRACY_GPU_ENABLED
    auto* profiler_ctx = instance.GetProfilerContext();
    if (profiler_ctx) {
        profiler_scope->~VkCtxScope();
        TracyVkCollect(profiler_ctx, current_cmdbuf);
    }
#endif

    if (on_submit) {
        on_submit(info);
    }

    EndRendering();
    if (auto* profiler = GpuProfiler::Get(); profiler && profiler->Records(this)) {
        // Until the next submission's first timestamp: mostly the GPU waiting for it.
        profiler->Mark(0x5B317ull, [] { return std::string{"(between submissions: GPU idle)"}; });
    }
    const auto recording_start = mali_submit_sample ? MaliPerfStats::Clock::now()
                                                    : MaliPerfStats::TimePoint{};
    SyncRecording();
    FlushNativeDrawBatch(current_cmdbuf);
    // Guest memory copies into staging read by this submission (copy threads).
    WaitHostCopies();
    if (mali_submit_sample)
        MaliPerfStats::Record(MaliPerfStats::Stage::SubmitHostCopies, recording_start);
    Check(current_cmdbuf.end());

    if (mali_unlocked_submit_throttle) {
        // Overlap command recording and host copies with the older GPU work.
        // Keep the capacity limit; reserve the tick only after preparation.
        wait_for_capacity();
        const auto reserved = work_semaphore.NextTick();
        ASSERT_MSG(reserved == signal_value, "Scheduler submission tick changed during throttle");
    }
    const vk::Semaphore timeline = work_semaphore.Handle();
    info.AddSignal(timeline, signal_value);

    static constexpr std::array<vk::PipelineStageFlags, 4> wait_stage_masks = {
        vk::PipelineStageFlagBits::eAllCommands,
        // The second wait may be a sparse/BDA dependency, not a swapchain
        // acquisition. Vertex/compute/transfer consumers must also wait.
        vk::PipelineStageFlagBits::eAllCommands,
        vk::PipelineStageFlagBits::eAllCommands,
        vk::PipelineStageFlagBits::eAllCommands,
    };

    const vk::TimelineSemaphoreSubmitInfo timeline_si = {
        .waitSemaphoreValueCount = info.num_wait_semas,
        .pWaitSemaphoreValues = info.wait_ticks.data(),
        .signalSemaphoreValueCount = info.num_signal_semas,
        .pSignalSemaphoreValues = info.signal_ticks.data(),
    };

    const vk::SubmitInfo submit_info = {
        .pNext = &timeline_si,
        .waitSemaphoreCount = info.num_wait_semas,
        .pWaitSemaphores = info.wait_semas.data(),
        .pWaitDstStageMask = wait_stage_masks.data(),
        .commandBufferCount = 1U,
        .pCommandBuffers = &current_cmdbuf,
        .signalSemaphoreCount = info.num_signal_semas,
        .pSignalSemaphores = info.signal_semas.data(),
    };

    ImGui::Core::TextureManager::Submit();
    const auto queue_start = mali_submit_sample ? MaliPerfStats::Clock::now()
                                                : MaliPerfStats::TimePoint{};
    if (work_semaphore.TraceEnabled()) {
        submit_history.tick = signal_value;
        submit_history.wait_count = info.num_wait_semas;
        submit_history.signal_count = info.num_signal_semas;
        for (u32 i=0; i<info.num_wait_semas && i<submit_history.wait_values.size(); ++i) {
            submit_history.wait_values[i] = info.wait_ticks[i];
            submit_history.wait_handles[i] = std::bit_cast<u64>(info.wait_semas[i]);
        }
        work_semaphore.TraceSubmission(submit_history);
        submit_history = {};
    }
    auto submit_result = instance.GetGraphicsQueue().submit(submit_info, info.fence);
    if (submit_result != vk::Result::eSuccess) work_semaphore.DumpSubmissionHistory(signal_value);
    if (mali_submit_sample)
        MaliPerfStats::Record(MaliPerfStats::Stage::SubmitQueueDriver, queue_start);
    ASSERT_MSG(submit_result == vk::Result::eSuccess, "Queue submit failed: {}",
               vk::to_string(submit_result));

    // On Android, completion is cached and advanced by the bounded wait
    // above, explicit guest readback waits, or the deferred-ops poller (which
    // already throttles Refresh calls). Never refresh unconditionally here.
    if (!bounded_submit) {
        work_semaphore.Refresh();
    }
    AllocateWorkerCommandBuffers();

    // Apply pending operations
    PopPendingOperations();
}

void Scheduler::PriorityPendingOpsThread(std::stop_token stoken) {
    Common::SetCurrentThreadName("shadPS4:GpuSchedPriorityPendingOpsRunner");

    while (!stoken.stop_requested()) {
        PendingOp op;
        {
            std::unique_lock lk(priority_pending_ops_mutex);
            priority_pending_ops_cv.wait(lk, stoken,
                                         [this] { return !priority_pending_ops.empty(); });
            if (stoken.stop_requested()) {
                break;
            }

            op = std::move(priority_pending_ops.front());
            priority_pending_ops.pop();
        }

        work_semaphore.Wait(op.gpu_tick);
        if (stoken.stop_requested()) {
            break;
        }

        op.callback();
    }
}

void DynamicState::Commit(const Instance& instance, const vk::CommandBuffer& cmdbuf) {
    // A null command buffer only updates the dirty flags, exactly as recording would.
    CommitWith(instance.IsDepthBoundsSupported(), instance.IsDynamicColorWriteMaskSupported(),
               instance.IsAttachmentFeedbackLoopLayoutSupported(), [&](auto&& command) {
                   if (cmdbuf) {
                       command(cmdbuf);
                   }
               });
}

} // namespace Vulkan
