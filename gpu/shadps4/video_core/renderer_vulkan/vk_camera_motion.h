// SPDX-License-Identifier: GPL-2.0-or-later
// gow3: camera motion vectors for temporal upscaling (docs/upscaler.md). The scene constants
// give the camera of each frame; the previous one is kept here. GOW3_DEBUG_MOTION=1 blends the
// motion vectors as colors into the frame before it is copied to the display.

#pragma once

#include <array>
#include <cstddef>
#include <cmath>
#include <vector>

#include "common/types.h"
#include "video_core/renderer_vulkan/vk_common.h"
#include "video_core/buffer_cache/buffer.h"
#include "video_core/texture_cache/image.h"

namespace VideoCore {
class TextureCache;
}

namespace Vulkan {

class Instance;
class Scheduler;
class Runtime;
class ObjectMotion;

class CameraMotion {
public:
    CameraMotion(const Instance& instance, Scheduler& scheduler,
                 VideoCore::TextureCache& texture_cache, Runtime& runtime);
    ~CameraMotion();
    void InvalidateHistory() { current.valid = previous.valid = false; }
    void SetObjectMotion(ObjectMotion* motion) noexcept {
        object_motion = motion;
    }
    /// This frame's object motion image (after RecordMotion), for the debug view; or null.
    vk::ImageView ObjectMotionView() const noexcept;
    vk::Image ObjectMotionImage(u32 width, u32 height) const noexcept;

    void SetJitter(std::array<float, 2> value) noexcept {
        previous_jitter = jitter;
        jitter = value;
    }

    [[nodiscard]] bool Enabled() const noexcept {
        return debug_overlay || for_upscaler;
    }

    /// Both cameras and the scene depth of the current frame are known.
    [[nodiscard]] bool Ready() const noexcept {
        return current.valid && previous.valid && depth_id;
    }
    // Diagnostic-only visibility into *why* a temporal dispatch has no history.
    // Zero overhead in normal builds except when the GSR2 diagnostic log runs.
    [[nodiscard]] u32 Gsr2HistoryDebugFlags() const noexcept {
        return (u32(current.valid) << 0) | (u32(previous.valid) << 1) |
               (u32(bool(depth_id)) << 2) | (u32(current.shader_hash != 0) << 3) |
               (u32(previous.shader_hash != 0) << 4) |
               (u32(frame_has_camera) << 5) |
               (u32(previous_frame_candidate.valid) << 6) |
               (u32(current_frame_candidate.valid) << 7);
    }
    [[nodiscard]] u64 Gsr2CurrentShaderDebug() const noexcept {
        return current.shader_hash;
    }
    [[nodiscard]] u64 Gsr2PreviousShaderDebug() const noexcept {
        return previous.shader_hash;
    }
    // R14 applies stricter temporal validity only to GSR2. Other upscalers
    // continue using Ready(), unchanged.
    enum class Gsr2HistoryStatus : u32 {
        Valid = 0, MissingCamera, DifferentShader, ProjectionCut, PositionCut, RotationCut
    };
    [[nodiscard]] Gsr2HistoryStatus Gsr2HistoryValidity() const noexcept {
        if (!Ready() || !current.shader_hash || !previous.shader_hash)
            return Gsr2HistoryStatus::MissingCamera;
        if (current.shader_hash != previous.shader_hash)
            return Gsr2HistoryStatus::DifferentShader;
        for (unsigned i = 0; i < 4; ++i) {
            const float a = current.proj[i], b = previous.proj[i];
            if (!std::isfinite(a) || !std::isfinite(b))
                return Gsr2HistoryStatus::ProjectionCut;
            if (std::abs(a - b) > (i < 2 ? 0.055f : 0.008f))
                return Gsr2HistoryStatus::ProjectionCut;
        }
        float displacement_sq = 0.f;
        for (unsigned r = 0; r < 3; ++r) {
            const float a = current.inv_view[r * 4 + 3];
            const float b = previous.inv_view[r * 4 + 3];
            if (!std::isfinite(a) || !std::isfinite(b))
                return Gsr2HistoryStatus::PositionCut;
            displacement_sq += (a - b) * (a - b);
        }
        if (displacement_sq > 64.f) return Gsr2HistoryStatus::PositionCut;
        float forward_dot = 0.f, norms[2]{};
        for (unsigned k = 0; k < 3; ++k) {
            const float a = current.view[8 + k], b = previous.view[8 + k];
            if (!std::isfinite(a) || !std::isfinite(b))
                return Gsr2HistoryStatus::RotationCut;
            forward_dot += a * b;
            norms[0] += a * a;
            norms[1] += b * b;
        }
        if (norms[0] < 0.9f || norms[1] < 0.9f ||
            forward_dot < 0.90f * std::sqrt(norms[0] * norms[1]))
            return Gsr2HistoryStatus::RotationCut;
        return Gsr2HistoryStatus::Valid;
    }
    // Snapshot the most recently completed scene BEFORE OnDisplayPass clears
    // current/depth for the next frame. Presenter consumes it after guest UI
    // and VideoOut copying; never use next-frame live camera with old pixels.
    [[nodiscard]] Gsr2HistoryStatus CompletedHistoryValidity() const noexcept {
        return completed_history_status;
    }
    [[nodiscard]] VideoCore::ImageId CompletedDepth() const noexcept {
        return completed_depth;
    }
    [[nodiscard]] VAddr CompletedVideoOutAddress() const noexcept {
        return completed_videoout_address;
    }
    [[nodiscard]] u64 CompletedVideoOutGeneration() const noexcept {
        return completed_videoout_generation;
    }
    [[nodiscard]] std::array<float, 2> CompletedJitter() const noexcept { return completed_current_jitter; }
    [[nodiscard]] float CompletedVerticalFov() const noexcept {
        return 2.0f * std::atan(1.0f / completed_current.proj[1]);
    }
    [[nodiscard]] bool CompletedCameraStill() const noexcept {
        if (completed_history_status != Gsr2HistoryStatus::Valid) return false;
        float diff = 0.0f;
        for (size_t i = 0; i < completed_current.view.size(); ++i)
            diff += std::abs(completed_current.view[i] - completed_previous.view[i]);
        for (size_t i = 0; i < completed_current.proj.size(); ++i)
            diff += std::abs(completed_current.proj[i] - completed_previous.proj[i]);
        return diff < 1e-5f;
    }
    void RecordCompletedMotion(vk::CommandBuffer cmdbuf, vk::ImageView depth_view,
                               vk::ImageView motion_view, u32 width, u32 height);

    [[nodiscard]] VideoCore::ImageId Depth() const noexcept {
        return depth_id;
    }
    /// The render size in the scene constants (the game's viewport; its targets may be
    /// allocated larger, e.g. 1916x1080 for a 1916x1078 scene), or zero before the first camera.
    [[nodiscard]] std::array<u32, 2> RenderSize() const noexcept {
        return render_size;
    }
    /// Vertical field of view and near/far planes of the current camera.
    [[nodiscard]] float VerticalFov() const noexcept;
    [[nodiscard]] float Near() const noexcept;
    // Upstream zFitness GSR2: use the more expensive 9-tap reconstruction
    // only when BOTH the view and projection matrices remained unchanged.
    [[nodiscard]] bool CameraStill() const noexcept {
        if (!current.valid || !previous.valid) return false;
        float diff = 0.0f;
        for (size_t i = 0; i < current.view.size(); ++i)
            diff += std::abs(current.view[i] - previous.view[i]);
        for (size_t i = 0; i < current.proj.size(); ++i)
            diff += std::abs(current.proj[i] - previous.proj[i]);
        return diff < 1e-5f;
    }
    // Reference-centre motion predicted by independently validated guest matrices,
    // in render pixels. Useful to check that camera movement isn't being zero-filled.
    [[nodiscard]] std::array<float, 2> EstimatedMotion(u32 width, u32 height) const noexcept;
    // Current projection, previous projection, and row Z of previous-view * inverse-view.
    [[nodiscard]] std::array<std::array<float, 4>, 3> TaaDepthParameters() const noexcept;

    /// Records the motion vector pass: `depth_view` (depth aspect, General layout) into
    /// `motion_view` (RG16F storage, General), pixels, previous minus current.
    void RecordMotion(vk::CommandBuffer cmdbuf, vk::ImageView depth_view, vk::ImageView motion_view,
                      u32 width, u32 height);

    /// Scan bound scene vertex constants for algebraically validated camera matrices.
    /// Float count comes from the actual guest buffer, never assumed to be 864 bytes.
    void OnConstants(const float* data, size_t float_count, u64 shader_hash, u32 buffer_slot);

    /// The G-buffer pass (5+ color targets): its depth is the scene depth.
    void OnGBufferPass(VideoCore::ImageId depth);

    /// The pass copying the finished frame (`frame`, the last target drawn) to the display: the
    /// frame's depth and camera are complete. Records the debug overlay, starts a new frame.
    // Record the verified scene camera/depth at the FIRST actual draw into
    // the corresponding registered guest framebuffer, before the HUD's
    // vertex constants can replace the source camera.
    void OnDisplayTargetDraw(VAddr guest_address);
    void OnDisplayPass(VideoCore::ImageId frame, VAddr presented_guest_address = 0);

private:
    struct Camera {
        std::array<float, 12> view{};     ///< world to view, 3x4 rows
        std::array<float, 12> inv_view{}; ///< view to world, 3x4 rows
        std::array<float, 4> proj{};      ///< x scale, y scale, z scale, z offset
        u64 shader_hash = 0; ///< provenance of the recovered camera
        bool valid = false;
    };

    void RecordMotionFor(vk::CommandBuffer cmdbuf, vk::ImageView depth_view,
                         vk::ImageView motion_view, u32 width, u32 height,
                         const Camera& now, const Camera& before,
                         std::array<float, 2> now_jitter, std::array<float, 2> before_jitter,
                         bool include_object_motion);
    void Overlay(VideoCore::ImageId frame);

    const Instance& instance;
    Scheduler& scheduler;
    VideoCore::TextureCache& texture_cache;
    Runtime& runtime;
    bool debug_overlay = false;
    bool for_upscaler = false;
    vk::UniqueDescriptorSetLayout motion_desc_layout;
    vk::UniquePipelineLayout motion_pipeline_layout;
    vk::UniquePipeline motion_pipeline;

    ObjectMotion* object_motion = nullptr;
    Camera current, previous;
    Camera completed_current, completed_previous;
    std::array<float, 2> completed_current_jitter{}, completed_previous_jitter{};
    Gsr2HistoryStatus completed_history_status = Gsr2HistoryStatus::MissingCamera;
    VideoCore::ImageId completed_depth{};
    VAddr completed_videoout_address = 0;
    // Camera/depth provenance is recorded at the rendering boundary, not
    // manufactured later from Presenter::PrepareFrame's requested address.
    struct DisplayTargetCandidate {
        VAddr address = 0;
        Camera camera{};
        VideoCore::ImageId depth{};
        // ImageId alone is not a lifetime guarantee: TextureCache can recycle
        // its slot or rewrite the depth image after this guest display copy.
        u64 depth_image_uid = 0;
        u64 depth_alias_generation = 0;
    };
    static constexpr size_t MaxDisplayTargetCandidates = 32;
    std::array<DisplayTargetCandidate, MaxDisplayTargetCandidates> display_target_candidates{};
    u64 completed_videoout_generation = 0;
    // Single-frame camera sightings require confirmation on a neighboring display frame.
    // These candidates never become temporal history by themselves.
    Camera current_frame_candidate, previous_frame_candidate;
    // The game binds multiple distinct camera shaders during one forward
    // frame. A single candidate slot loses the previous frame's real scene
    // source when a postprocess/shadow shader appears last. Keep a bounded
    // per-shader set for ONLY the immediately preceding completed scene.
    static constexpr size_t MaxFrameCameraSources = 16;
    std::array<Camera, MaxFrameCameraSources> current_frame_sources{};
    std::array<Camera, MaxFrameCameraSources> previous_frame_sources{};
    bool frame_has_camera = false;
    bool have_pose = false, have_projection = false;
    std::array<float, 12> frame_view{}, frame_inverse{};
    std::array<float, 4> frame_projection{};
    u32 frame_pose_votes = 0, frame_scanned_buffers = 0;
    u32 frame_extra_source_probes = 0;
    u64 frame_camera_shader_hash = 0;
    bool reported_camera = false;
    // Bounded exact constant capture during two gameplay frames. Enables offline
    // mapping of eboot shader uniforms without repeated blind APK patches.
    u32 probe_frame = 0, probe_seen = 0, probe_written = 0;
    std::array<float, 2> jitter{}, previous_jitter{};
    std::array<u32, 2> render_size{};
    VideoCore::ImageId depth_id{};

    vk::UniqueDescriptorSetLayout desc_layout;
    vk::UniquePipelineLayout pipeline_layout;
    vk::UniquePipeline overlay_pipeline;
    /// Debug: the last two finished frames (RGBA8 packed), for the reprojection check.
    std::unique_ptr<VideoCore::Buffer> frames[2];
    u32 frame_index = 0;
};

} // namespace Vulkan
