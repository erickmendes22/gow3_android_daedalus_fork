// SPDX-License-Identifier: GPL-2.0-or-later
#include "video_core/renderer_vulkan/vk_camera_motion.h"
#include "video_core/renderer_vulkan/gow3_camera_layout.h"

#include <algorithm>
#include <bit>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "gow3_toggles.h"

#include "video_core/host_shaders/camera_motion_comp.h"
#include "video_core/host_shaders/camera_motion_debug_comp.h"
#include "video_core/renderer_vulkan/vk_instance.h"
#include "video_core/renderer_vulkan/vk_object_motion.h"
#include "video_core/renderer_vulkan/vk_runtime.h"
#include "video_core/renderer_vulkan/vk_scheduler.h"
#include "video_core/renderer_vulkan/vk_shader_util.h"
#include "video_core/texture_cache/texture_cache.h"

namespace Vulkan {

namespace {

struct PushConstants {
    std::array<float, 12> reproject;
    std::array<float, 4> proj;
    std::array<float, 4> prev_proj;
    std::array<float, 2> size;
    std::array<float, 2> jitter;
    std::array<float, 2> previous_jitter;
    u32 mode;
};

/// a * b for 3x4 affine matrices (rows [R | t]).
std::array<float, 12> Multiply(const std::array<float, 12>& a, const std::array<float, 12>& b) {
    std::array<float, 12> out{};
    for (int r = 0; r < 3; ++r) {
        for (int c = 0; c < 4; ++c) {
            float v = c == 3 ? a[r * 4 + 3] : 0.0f;
            for (int k = 0; k < 3; ++k) {
                v += a[r * 4 + k] * b[k * 4 + c];
            }
            out[r * 4 + c] = v;
        }
    }
    return out;
}

} // namespace

CameraMotion::CameraMotion(const Instance& instance_, Scheduler& scheduler_,
                           VideoCore::TextureCache& texture_cache_, Runtime& runtime_)
    : instance{instance_}, scheduler{scheduler_}, texture_cache{texture_cache_}, runtime{runtime_} {
    const char* env = std::getenv("GOW3_DEBUG_MOTION");
    debug_overlay = env && env[0] == '1';
    const char* upscaler = std::getenv("GOW3_UPSCALER");
    // The upscaler can be switched on from the menu at any time: the camera is always tracked
    // unless GOW3_UPSCALER=none.
    for_upscaler = !(upscaler && std::strcmp(upscaler, "none") == 0);
    const auto device = instance.GetDevice();
    if (for_upscaler) {
        const std::array<vk::DescriptorSetLayoutBinding, 3> motion_bindings = {{
            {.binding = 0,
             .descriptorType = vk::DescriptorType::eSampledImage,
             .descriptorCount = 1,
             .stageFlags = vk::ShaderStageFlagBits::eCompute},
            {.binding = 1,
             .descriptorType = vk::DescriptorType::eStorageImage,
             .descriptorCount = 1,
             .stageFlags = vk::ShaderStageFlagBits::eCompute},
            {.binding = 2,
             .descriptorType = vk::DescriptorType::eSampledImage,
             .descriptorCount = 1,
             .stageFlags = vk::ShaderStageFlagBits::eCompute},
        }};
        motion_desc_layout = Check(device.createDescriptorSetLayoutUnique({
            .flags = vk::DescriptorSetLayoutCreateFlagBits::ePushDescriptorKHR,
            .bindingCount = static_cast<u32>(motion_bindings.size()),
            .pBindings = motion_bindings.data(),
        }));
        const vk::PushConstantRange range{.stageFlags = vk::ShaderStageFlagBits::eCompute,
                                          .offset = 0,
                                          .size = sizeof(PushConstants)};
        motion_pipeline_layout = Check(device.createPipelineLayoutUnique({
            .setLayoutCount = 1,
            .pSetLayouts = &*motion_desc_layout,
            .pushConstantRangeCount = 1,
            .pPushConstantRanges = &range,
        }));
        const auto motion_module = CompileSPV(CAMERA_MOTION_COMP, device);
        motion_pipeline = Check(device.createComputePipelineUnique(
            {}, vk::ComputePipelineCreateInfo{
                    .stage = {.stage = vk::ShaderStageFlagBits::eCompute,
                              .module = motion_module,
                              .pName = "main"},
                    .layout = *motion_pipeline_layout,
                }));
        device.destroyShaderModule(motion_module);
    }
    if (!debug_overlay) {
        return;
    }
    const std::array<vk::DescriptorSetLayoutBinding, 4> bindings = {{
        {.binding = 0,
         .descriptorType = vk::DescriptorType::eSampledImage,
         .descriptorCount = 1,
         .stageFlags = vk::ShaderStageFlagBits::eCompute},
        {.binding = 1,
         .descriptorType = vk::DescriptorType::eStorageImage,
         .descriptorCount = 1,
         .stageFlags = vk::ShaderStageFlagBits::eCompute},
        {.binding = 2,
         .descriptorType = vk::DescriptorType::eStorageBuffer,
         .descriptorCount = 1,
         .stageFlags = vk::ShaderStageFlagBits::eCompute},
        {.binding = 3,
         .descriptorType = vk::DescriptorType::eStorageBuffer,
         .descriptorCount = 1,
         .stageFlags = vk::ShaderStageFlagBits::eCompute},
    }};
    desc_layout = Check(device.createDescriptorSetLayoutUnique({
        .flags = vk::DescriptorSetLayoutCreateFlagBits::ePushDescriptorKHR,
        .bindingCount = static_cast<u32>(bindings.size()),
        .pBindings = bindings.data(),
    }));
    const vk::PushConstantRange push_range{
        .stageFlags = vk::ShaderStageFlagBits::eCompute,
        .offset = 0,
        .size = sizeof(PushConstants),
    };
    pipeline_layout = Check(device.createPipelineLayoutUnique({
        .setLayoutCount = 1,
        .pSetLayouts = &*desc_layout,
        .pushConstantRangeCount = 1,
        .pPushConstantRanges = &push_range,
    }));
    const auto module = CompileSPV(CAMERA_MOTION_DEBUG_COMP, device);
    overlay_pipeline = Check(device.createComputePipelineUnique(
        {}, vk::ComputePipelineCreateInfo{
                .stage = {.stage = vk::ShaderStageFlagBits::eCompute,
                          .module = module,
                          .pName = "main"},
                .layout = *pipeline_layout,
            }));
    device.destroyShaderModule(module);
    for (auto& frame : frames) {
        frame = std::make_unique<VideoCore::Buffer>(instance, 0, 3840ull * 2160 * 4,
                                                    VideoCore::MemoryType::DeviceLocal);
    }
    std::printf("GPU: camera motion debug overlay on\n");
}

CameraMotion::~CameraMotion() = default;

float CameraMotion::VerticalFov() const noexcept {
    return 2.0f * std::atan(1.0f / current.proj[1]);
}

float CameraMotion::Near() const noexcept {
    // depth = zs + zo / z is 0 at the near plane.
    return -current.proj[3] / current.proj[2];
}

std::array<float, 2> CameraMotion::EstimatedMotion(u32 width, u32 height) const noexcept {
    if (!Ready() || !width || !height) return {};
    const auto reproject = Multiply(previous.view, current.inv_view);
    const float scene_z = 10.0f; // fixed reference point in view space, not a guessed game camera
    const float px = reproject[2] * scene_z + reproject[3];
    const float py = reproject[6] * scene_z + reproject[7];
    const float pz = reproject[10] * scene_z + reproject[11];
    if (!std::isfinite(px) || !std::isfinite(py) ||
        !std::isfinite(pz) || pz <= 0.001f) return {};
    const float dx = px / pz * previous.proj[0] * float(width) * 0.5f;
    const float dy = -py / pz * previous.proj[1] * float(height) * 0.5f;
    if (!std::isfinite(dx) || !std::isfinite(dy)) return {};
    return {dx, dy};
}

std::array<std::array<float, 4>, 3> CameraMotion::TaaDepthParameters() const noexcept {
    const auto transform = Multiply(previous.view, current.inv_view);
    return {current.proj, previous.proj,
            {transform[8], transform[9], transform[10], transform[11]}};
}

vk::ImageView CameraMotion::ObjectMotionView() const noexcept {
    return object_motion && object_motion->Enabled() ? object_motion->View() : vk::ImageView{};
}

vk::Image CameraMotion::ObjectMotionImage(u32 width, u32 height) const noexcept {
    return object_motion && object_motion->Enabled() ? object_motion->Image(width, height)
                                                      : vk::Image{};
}

void CameraMotion::RecordMotion(vk::CommandBuffer cmdbuf, vk::ImageView depth_view,
                                vk::ImageView motion_view, u32 width, u32 height) {
    RecordMotionFor(cmdbuf, depth_view, motion_view, width, height,
                    current, previous, jitter, previous_jitter, true);
}

void CameraMotion::RecordCompletedMotion(vk::CommandBuffer cmdbuf, vk::ImageView depth_view,
                                         vk::ImageView motion_view, u32 width, u32 height) {
    // Guest VideoOut is produced after OnDisplayPass. Use its frozen scene
    // camera rather than the reset camera of the next frame.
    RecordMotionFor(cmdbuf, depth_view, motion_view, width, height,
                    completed_current, completed_previous, {}, {}, false);
}

void CameraMotion::RecordMotionFor(vk::CommandBuffer cmdbuf, vk::ImageView depth_view,
                                   vk::ImageView motion_view, u32 width, u32 height,
                                   const Camera& now, const Camera& before,
                                   std::array<float, 2> now_jitter,
                                   std::array<float, 2> before_jitter,
                                   bool include_object_motion) {
    bool object_valid = false;
    const vk::ImageView object_view = include_object_motion && object_motion && object_motion->Enabled()
        ? object_motion->PrepareRead(cmdbuf, width, height, object_valid) : depth_view;
    const PushConstants push{
        .reproject = Multiply(before.view, now.inv_view),
        .proj = now.proj,
        .prev_proj = before.proj,
        .size = {float(width), float(height)},
        .jitter = now_jitter,
        .previous_jitter = before_jitter,
        .mode = object_valid ? 1u : 0u,
    };
    const vk::DescriptorImageInfo depth_info{.imageView = depth_view,
                                             .imageLayout = vk::ImageLayout::eGeneral};
    const vk::DescriptorImageInfo motion_info{.imageView = motion_view,
                                              .imageLayout = vk::ImageLayout::eGeneral};
    const vk::DescriptorImageInfo object_info{.imageView = object_view,
                                              .imageLayout = vk::ImageLayout::eGeneral};
    const std::array<vk::WriteDescriptorSet, 3> writes = {{
        {.dstBinding = 0,
         .descriptorCount = 1,
         .descriptorType = vk::DescriptorType::eSampledImage,
         .pImageInfo = &depth_info},
        {.dstBinding = 1,
         .descriptorCount = 1,
         .descriptorType = vk::DescriptorType::eStorageImage,
         .pImageInfo = &motion_info},
        {.dstBinding = 2,
         .descriptorCount = 1,
         .descriptorType = vk::DescriptorType::eSampledImage,
         .pImageInfo = &object_info},
    }};
    cmdbuf.bindPipeline(vk::PipelineBindPoint::eCompute, *motion_pipeline);
    cmdbuf.pushDescriptorSetKHR(vk::PipelineBindPoint::eCompute, *motion_pipeline_layout, 0,
                                writes);
    cmdbuf.pushConstants(*motion_pipeline_layout, vk::ShaderStageFlagBits::eCompute, 0,
                         sizeof(push), &push);
    cmdbuf.dispatch((width + 7) / 8, (height + 7) / 8, 1);
}

void CameraMotion::OnConstants(const float* data, size_t float_count, u64 shader_hash, u32 buffer_slot) {
    // Keep the old validated Bloodborne layout for the desktop/non-GoW3 path.
    // The CUSA01715 path below deliberately does not inherit those offsets.
    const char* selected_upscaler = std::getenv("GOW3_UPSCALER");
    const bool gow3_android_gsr2 = std::getenv("GOW3_ANDROID_PORT") &&
                                   selected_upscaler && std::strcmp(selected_upscaler, "gsr2") == 0;
    if (!std::getenv("GOW3_ANDROID_FSR_FIXED_OUTPUT") && !gow3_android_gsr2) {
        if (!data || float_count < 192 || frame_has_camera) return;
        if (data[0] != 3000.0f || data[4] < 64.0f || data[5] < 64.0f ||
            std::abs(data[1] * data[0] - 1.0f) > 1e-3f) return;
        std::memcpy(current.view.data(), data + 8, 12 * sizeof(float));
        std::memcpy(current.inv_view.data(), data + 180, 12 * sizeof(float));
        current.proj = {data[52], data[57], data[62], data[63]};
        current.valid = current.proj[0] != 0.0f && current.proj[1] != 0.0f;
        render_size = {u32(data[4]), u32(data[5])};
        frame_has_camera = current.valid;
        return;
    }
    // GoW III CUSA01715 does not use Bloodborne's far=3000, offset+8/+180
    // 864-byte signature. Inspect matrices actually bound by scene shaders.
    // Only algebraically inverse rigid transforms and valid perspective
    // projections are accepted; never synthesize a valid camera from zeros.
    if (!depth_id || !data || float_count < 16 || float_count > 1024)
        return;
    if (gow3_android_gsr2) {
        // GSR2 previously received no camera constants at all because the
        // caller required the FSR-only environment flag. Prove real input
        // delivery without dumping private guest data or flooding the log.
        static unsigned seen_blocks = 0;
        ++seen_blocks;
        if (seen_blocks <= 6 || seen_blocks == 1200 || seen_blocks % 600000 == 0) {
            std::printf("GSR2_CAMERA_FEED blocks=%u floats=%zu projection=%d pose=%d votes=%u\n",
                        seen_blocks, float_count, int(have_projection),
                        int(have_pose), frame_pose_votes);
        }
    }
    // eboot CUSA01623 exposes PS3_PreProjToProjMat, PS3_ModelToPreProjMat,
    // PS3_PrevModelToPreProjMat and PS3_InvProjFactors. These are not guaranteed
    // to be an affine + inverse pair in one constant block, as the old matcher
    // assumes. Collect a bounded selection of ACTUAL shader constants once
    // during gameplay to identify their layout by shader hash and buffer slot.
    // Do not mark camera valid or disturb GSR2 history without real evidence.
    if (gow3_android_gsr2 && probe_frame && probe_seen < 1024 &&
        float_count >= 16 && float_count <= 1024) {
        ++probe_seen;
        if (probe_written < 32 &&
            (probe_seen <= 8 || probe_seen % 32 == 0)) {
            ++probe_written;
            // Print at most 512 floats in <=128-float chunks so Android logs
            // do not truncate long messages and 384/420-float uniform blocks
            // retain matrices beyond their first 128 entries.
            const size_t limit = std::min(float_count, size_t(512));
            for (size_t start = 0; start < limit; start += 128) {
                char hex[1200]{};
                size_t written = 0;
                const size_t count = std::min(size_t(128), limit - start);
                for (size_t i = 0; i < count && written + 10 < sizeof(hex); ++i) {
                    const int n = std::snprintf(hex + written, sizeof(hex) - written,
                                                "%08x", std::bit_cast<u32>(data[start + i]));
                    if (n <= 0) break;
                    written += size_t(n);
                }
                std::printf("GSR2_CAMERA_RAW frame=%u sample=%u shader=%016llx slot=%u floats=%zu offset=%zu count=%zu hex=%s\n",
                            probe_frame, probe_written,
                            static_cast<unsigned long long>(shader_hash), buffer_slot,
                            float_count, start, count, hex);
            }
            std::fflush(stdout);
        }
    }
    // GoW3 Bionic: use the ACTUAL world->clip matrix at float offset 16 of
    // the captured vertex slot 1. Its independent projection/position have
    // been verified against other shader constants in the 22:00 eboot log.
    // Unlike FindPose(), this correctly handles GoW3's two separate
    // model/preprojection matrices, not Bloodborne's adjacent inverse pair.
    // An unproven legacy affine-pair candidate has no shader provenance.
    // Do not let it suppress the exact GoW3 view-projection detector for the
    // rest of the display frame, especially after a scene or shader change.
    if (frame_has_camera && frame_pose_votes >= 3 &&
        (!gow3_android_gsr2 || current.shader_hash != 0)) {
        // The selected frame camera is already proven. In GSR2, continue
        // collecting previously unseen vertex-shader camera sources for the
        // next display frame; the old unconditional return made the 16-entry
        // adjacent-frame cache effectively a single-shader cache.
        // Never rescan a recovered shader or exceed 64 additional probes.
        if (!gow3_android_gsr2 || buffer_slot != 1 ||
            frame_extra_source_probes >= 64)
            return;
        for (const auto& source : current_frame_sources)
            if (source.valid && source.shader_hash == shader_hash)
                return;
        ++frame_extra_source_probes;
    }
    if (gow3_android_gsr2 && buffer_slot == 1 && float_count >= 32) {
        const auto recovered = Gow3CameraLayout::RecoverViewProjection(
            data, float_count, buffer_slot);
        if (recovered.valid) {
            // Prefer a recovered source seen in the preceding display frame.
            // This helps cinematic/cutscene shaders which bind a valid camera
            // only once per frame, without accepting arbitrary new matrices.
            const Camera* prior_source = nullptr;
            for (const auto& candidate : previous_frame_sources) {
                if (candidate.valid && candidate.shader_hash == shader_hash) {
                    prior_source = &candidate;
                    break;
                }
            }
            // Preserve the original last-frame candidate as an independent
            // fallback, including for any overflow of the bounded source set.
            const bool legacy_previous_match =
                previous_frame_candidate.valid &&
                previous_frame_candidate.shader_hash == shader_hash;
            if (!prior_source && legacy_previous_match)
                prior_source = &previous_frame_candidate;
            const bool same_source_last_frame = prior_source != nullptr;
            // One saved camera per shader, never more than the fixed 16.
            // These entries are discarded at EVERY display boundary, so a
            // scene cut cannot revive stale camera transforms.
            Camera* source_slot = nullptr;
            for (auto& candidate : current_frame_sources) {
                if (candidate.valid && candidate.shader_hash == shader_hash) {
                    source_slot = &candidate;
                    break;
                }
            }
            if (!source_slot) {
                for (auto& candidate : current_frame_sources) {
                    if (!candidate.valid) {
                        source_slot = &candidate;
                        break;
                    }
                }
            }
            if (source_slot) {
                source_slot->view = recovered.view;
                source_slot->inv_view = recovered.inverse;
                source_slot->proj = recovered.projection;
                source_slot->shader_hash = shader_hash;
                source_slot->valid = true;
            }
            if (!current_frame_candidate.valid ||
                (same_source_last_frame &&
                 current_frame_candidate.shader_hash != shader_hash)) {
                current_frame_candidate.view = recovered.view;
                current_frame_candidate.inv_view = recovered.inverse;
                current_frame_candidate.proj = recovered.projection;
                current_frame_candidate.shader_hash = shader_hash;
                current_frame_candidate.valid = true;
            }
            bool adjacent_confirmed = false;
            if (gow3_android_gsr2 && same_source_last_frame) {
                Gow3CameraLayout::GoW3ViewProjection earlier{};
                earlier.view = prior_source->view;
                earlier.inverse = prior_source->inv_view;
                earlier.projection = prior_source->proj;
                earlier.position = {
                    earlier.inverse[3], earlier.inverse[7], earlier.inverse[11]};
                earlier.valid = true;
                adjacent_confirmed =
                    Gow3CameraLayout::CompatibleAdjacentCameraSamples(earlier, recovered);
                if (adjacent_confirmed && !legacy_previous_match) {
                    static unsigned multi_source_matches = 0;
                    if (++multi_source_matches <= 4 || multi_source_matches % 1200 == 0)
                        std::printf("GSR2_CAMERA_MULTI_SOURCE_RECOVERED count=%u shader=%016llx\n",
                                    multi_source_matches,
                                    static_cast<unsigned long long>(shader_hash));
                }
            }
            // Draw calls within a scene may move slightly (animated camera).
            // Demand two independently bound coherent camera projections
            // before allowing temporal history to be used.
            bool coherent = have_pose && have_projection &&
                            frame_camera_shader_hash == shader_hash;
            if (coherent) {
                if (std::abs(frame_projection[0] - recovered.projection[0]) > 0.09f ||
                    std::abs(frame_projection[1] - recovered.projection[1]) > 0.16f ||
                    std::abs(frame_projection[3] - recovered.projection[3]) > 0.005f)
                    coherent = false;
                for (unsigned i = 0; i < 3; ++i)
                    if (std::abs(frame_inverse[i * 4 + 3] -
                                 recovered.inverse[i * 4 + 3]) > 1.5f)
                        coherent = false;
            }
            if (coherent) {
                frame_pose_votes = std::min(frame_pose_votes + 1, 3u);
            } else if (adjacent_confirmed) {
                // Two independent display frames, same proven shader and
                // geometrically continuous camera. This only verifies CURRENT
                // frame; last frame's invalid GSR2 history remains reset.
                frame_pose_votes = 2;
                static unsigned regained = 0;
                if (++regained <= 6 || regained % 600 == 0)
                    std::printf("GSR2_CAMERA_REACQUIRED shader=%016llx frame_confirmed=2 count=%u\n",
                                static_cast<unsigned long long>(shader_hash), regained);
            } else {
                frame_pose_votes = 1;
            }
            // The freshest pose matches the actual completed scene. The
            // camera position is independently verified, not inferred from
            // a guessed fixed FOV or artificial motion vector.
            frame_view = recovered.view;
            frame_inverse = recovered.inverse;
            frame_projection = recovered.projection;
            frame_camera_shader_hash = shader_hash;
            have_pose = have_projection = true;
            if (frame_pose_votes >= 2 &&
                (!gow3_android_gsr2 || !current.valid || !current.shader_hash ||
                 current.shader_hash == frame_camera_shader_hash)) {
                // Do not replace a verified scene camera with a different
                // later shadow/postprocess shader. Keep the extra source in
                // current_frame_sources for next-frame correlation instead.
                current.view = frame_view;
                current.inv_view = frame_inverse;
                current.proj = frame_projection;
                current.shader_hash = frame_camera_shader_hash;
                current.valid = true;
                frame_has_camera = true;
                static unsigned confirmed = 0;
                if (++confirmed <= 3 || confirmed % 2400 == 0)
                    std::printf("GOW3_CAMERA_VERIFIED_VP shader=%016llx slot=%u sx=%.5f sy=%.5f near=%.5f world=(%.3f,%.3f,%.3f) votes=%u\n",
                                static_cast<unsigned long long>(shader_hash), buffer_slot,
                                recovered.projection[0], recovered.projection[1],
                                recovered.near_plane, recovered.position[0],
                                recovered.position[1], recovered.position[2], frame_pose_votes);
            }
            return;
        }
    }
    // The forward renderer binds many constant buffers per draw. An exhaustive
    // affine-pair search can consume the GPU command CPU thread, becoming more
    // expensive than the FSR dispatch it is trying to enable. Cap expensive
    // discovery to six blocks per frame while no verified layout is known.
    // Retain this across present frames only for the current selected frame.
    if (++frame_scanned_buffers > 6) return;

    if (!have_projection) {
        const auto lens = Gow3CameraLayout::FindProjection(data, float_count);
        if (lens.valid) {
            frame_projection = lens.projection;
            have_projection = true;
            if (!reported_camera)
                std::printf("GOW3_CAMERA_LENS offset=%u sx=%g sy=%g z=%g dz=%g\n",
                            lens.offset, frame_projection[0], frame_projection[1],
                            frame_projection[2], frame_projection[3]);
        }
    }
    if (!have_pose || frame_pose_votes < 3) {
        const auto pose = Gow3CameraLayout::FindPose(data, float_count);
        if (pose.valid) {
            if (!have_pose) {
                frame_view = pose.view;
                frame_inverse = pose.inverse;
                have_pose = true;
                frame_pose_votes = 1;
                if (!reported_camera)
                    std::printf("GOW3_CAMERA_PAIR view_offset=%u inverse_offset=%u bytes=%zu\n",
                                pose.view_offset, pose.inverse_offset,
                                float_count * sizeof(float));
            } else if (Gow3CameraLayout::SimilarPose(frame_view, pose.view) &&
                       Gow3CameraLayout::SimilarPose(frame_inverse, pose.inverse)) {
                ++frame_pose_votes; // a shared scene camera is bound to many draws
            }
        }
    }
    // A recovered, shader-proven GoW III view/projection always outranks
    // the legacy unconstrained FindPose/FindProjection pair. The latter may
    // see unrelated model or UI constants later in the SAME display frame.
    // Previously this branch overwrote current.shader_hash with 0 after an
    // adjacent verified recovery (2 votes), breaking temporal history.
    // Keep scanning exact RecoverViewProjection() above on following calls;
    // only prevent a lower-confidence candidate from replacing a verified one.
    const bool keep_verified_camera =
        gow3_android_gsr2 && current.valid && current.shader_hash != 0;
    if (have_pose && have_projection && frame_pose_votes >= 2 && keep_verified_camera) {
        static unsigned protected_frames = 0;
        if (++protected_frames <= 4 || protected_frames % 1200 == 0)
            std::printf("GSR2_CAMERA_PROVENANCE_PROTECTED count=%u shader=%016llx legacy_votes=%u\n",
                        protected_frames,
                        static_cast<unsigned long long>(current.shader_hash),
                        frame_pose_votes);
    }
    if (have_pose && have_projection && frame_pose_votes >= 2 &&
        !keep_verified_camera) {
        current.view = frame_view;
        current.inv_view = frame_inverse;
        current.proj = frame_projection;
        // FindPose + FindProjection may represent unrelated guest draws.
        // Until RecoverViewProjection confirms provenance, a legacy pair
        // can guide discovery but must NEVER satisfy GSR2 temporal history.
        current.shader_hash = 0;
        current.valid = true;
        frame_has_camera = true;
        if (!reported_camera) {
            reported_camera = true;
            std::printf("GOW3_CAMERA_VERIFIED pair=1 projection=1 votes=%u depth=%d\n",
                        frame_pose_votes, int(bool(depth_id)));
        }
    }
}

void CameraMotion::OnGBufferPass(VideoCore::ImageId depth) {
    depth_id = depth;
}

void CameraMotion::OnDisplayPass(VideoCore::ImageId frame, VAddr presented_guest_address) {
    const char* selected = std::getenv("GOW3_UPSCALER");
    if (std::getenv("GOW3_ANDROID_FSR_FIXED_OUTPUT") ||
        (std::getenv("GOW3_ANDROID_PORT") && selected && !std::strcmp(selected, "gsr2"))) {
        static u32 camera_frames = 0;
        const u32 frame_number = ++camera_frames;
        // R12 recovered the real camera offsets. Keep raw floating-point
        // constant dumping available only as an explicit forensic opt-in,
        // not on every regular R13 test session.
        if (std::getenv("GOW3_GSR2_CAMERA_LAYOUT_PROBE") &&
            selected && !std::strcmp(selected, "gsr2") &&
            std::getenv("GOW3_ANDROID_PORT") &&
            (frame_number == 1200 || frame_number == 3600)) {
            probe_frame = frame_number;
            probe_seen = probe_written = 0;
            std::printf("GSR2_CAMERA_RAW_CAPTURE arm=%u max_samples=32 max_blocks=1024\n", probe_frame);
        }
        // Include gameplay, not only the six loading-screen frames as before.
        if (frame_number == 1 || frame_number == 600 || frame_number == 1800 ||
            frame_number == 3600 || frame_number == 6000) {
            std::printf("GOW3_FSR_CAMERA frame=%u captured=%d current=%d previous=%d depth=%d scene=%ux%u\n",
                        frame_number, int(frame_has_camera), int(current.valid),
                        int(previous.valid), int(bool(depth_id)),
                        render_size[0], render_size[1]);
        }
    }
    if (debug_overlay && frame && depth_id && current.valid && previous.valid) {
        Overlay(frame);
    }
    // Consecutive-frame recovery is a separate evidence channel from actual
    // history. A frame with no valid recovered sample must break that chain.
    const char* chosen = std::getenv("GOW3_UPSCALER");
    if (std::getenv("GOW3_ANDROID_PORT") && chosen &&
        std::strcmp(chosen, "gsr2") == 0) {
        previous_frame_candidate = current_frame_candidate;
        current_frame_candidate.valid = false;
        if (std::getenv("GOW3_GSR2_DIRECT_VIDEOOUT")) {
            static unsigned source_frames = 0;
            ++source_frames;
            if (source_frames <= 4 || source_frames % 600 == 0) {
                unsigned unique_sources = 0;
                for (const auto& source : current_frame_sources)
                    unique_sources += unsigned(source.valid);
                std::printf("GSR2_CAMERA_SOURCE_POOL frame=%u unique=%u extra_probes=%u selected_shader=%016llx\n",
                            source_frames, unique_sources, frame_extra_source_probes,
                            static_cast<unsigned long long>(current.shader_hash));
            }
        }
        previous_frame_sources = current_frame_sources;
        current_frame_sources = {};
        frame_extra_source_probes = 0;
    }
    // Preserve the completed scene's true depth and verified adjacent cameras
    // for the later Presenter VideoOut dispatch. This cannot be reconstructed
    // from live camera state because we clear it below.
    completed_history_status = frame_has_camera && current.valid
        ? Gsr2HistoryValidity() : Gsr2HistoryStatus::MissingCamera;
    completed_current = current;
    completed_previous = previous;
    completed_depth = depth_id;
    // Only the real Presenter::PrepareFrame flip has an address. Ordinary
    // display draws and Native AA never acquire a GSR2 frame generation.
    completed_videoout_address = presented_guest_address;
    if (presented_guest_address)
        ++completed_videoout_generation;
    if (std::getenv("GOW3_GSR2_DIRECT_VIDEOOUT")) {
        static unsigned snapshots = 0, eligible = 0;
        ++snapshots;
        eligible += completed_history_status == Gsr2HistoryStatus::Valid;
        if (snapshots <= 4 || snapshots % 600 == 0)
            std::printf("GSR2_COMPLETED_SCENE frame=%u status=%u valid_total=%u depth=%d shader=%llx/%llx\n",
                snapshots, unsigned(completed_history_status), eligible, int(bool(completed_depth)),
                (unsigned long long)completed_current.shader_hash,
                (unsigned long long)completed_previous.shader_hash);
    }
    // Freeze the just completed scene camera as the previous frame. The next
    // scene must acquire its own transform before history may be reprojected.
    if (frame_has_camera && current.valid) {
        previous = current;
    } else {
        InvalidateHistory();
    }
    current.valid = false;
    // Shader provenance belongs to the finished frame. Never let the
    // unverified legacy path inherit a previous frame's shader hash.
    current.shader_hash = 0;
    frame_has_camera = false;
    have_pose = have_projection = false;
    frame_pose_votes = frame_scanned_buffers = 0;
    frame_camera_shader_hash = 0;
    depth_id = {};
}

void CameraMotion::Overlay(VideoCore::ImageId frame) {
    auto& depth = texture_cache.GetImage(depth_id);
    auto& color = texture_cache.GetImage(frame);
    const auto depth_format = depth.info.pixel_format;
    if ((depth_format != vk::Format::eD32Sfloat && depth_format != vk::Format::eD32SfloatS8Uint) ||
        color.info.pixel_format != vk::Format::eR8G8B8A8Unorm ||
        !(color.usage_flags & vk::ImageUsageFlagBits::eStorage) ||
        color.info.size.width != depth.info.size.width ||
        color.info.size.height != depth.info.size.height) {
        static bool warned = false;
        if (!warned) {
            warned = true;
            std::printf("Camera motion: overlay skipped (depth %s, frame %s %ux%u)\n",
                        vk::to_string(depth_format).c_str(),
                        vk::to_string(color.info.pixel_format).c_str(), color.info.size.width,
                        color.info.size.height);
        }
        return;
    }
    const auto device = instance.GetDevice();
    const auto depth_view = Check(device.createImageView({
        .image = vk::Image(depth.backing->image),
        .viewType = vk::ImageViewType::e2D,
        .format = depth_format,
        .subresourceRange = {vk::ImageAspectFlagBits::eDepth, 0, 1, 0, 1},
    }));
    const auto color_view = Check(device.createImageView({
        .image = vk::Image(color.backing->image),
        .viewType = vk::ImageViewType::e2D,
        .format = vk::Format::eR8G8B8A8Unorm,
        .subresourceRange = {vk::ImageAspectFlagBits::eColor, 0, 1, 0, 1},
    }));

    scheduler.EndRendering();
    runtime.Transit(&depth, vk::ImageLayout::eGeneral, vk::PipelineStageFlagBits2::eComputeShader,
                    vk::AccessFlagBits2::eShaderRead);
    runtime.Transit(&color, vk::ImageLayout::eGeneral, vk::PipelineStageFlagBits2::eComputeShader,
                    vk::AccessFlagBits2::eShaderRead | vk::AccessFlagBits2::eShaderWrite);
    runtime.FlushBarriers();

    const PushConstants push{
        .reproject = Multiply(previous.view, current.inv_view),
        .proj = current.proj,
        .prev_proj = previous.proj,
        .size = {float(color.info.size.width), float(color.info.size.height)},
        .jitter = jitter,
        .previous_jitter = previous_jitter,
        .mode = Gow3Toggle::Disabled(1u << 20)   ? 1u
                : Gow3Toggle::Disabled(1u << 21) ? 2u
                : Gow3Toggle::Disabled(1u << 22) ? 3u
                : Gow3Toggle::Disabled(1u << 23) ? 4u
                                               : 0u,
    };
    static u32 log_counter = 0;
    if (++log_counter % 200 == 0) {
        const auto& m = push.reproject;
        std::printf("Camera motion: proj %g %g %g %g prev %g %g %g %g\n"
                    "  view  %8.4f %8.4f %8.4f %9.3f | %8.4f %8.4f %8.4f %9.3f | %8.4f %8.4f %8.4f %9.3f\n"
                    "  reproj %8.4f %8.4f %8.4f %9.4f | %8.4f %8.4f %8.4f %9.4f | %8.4f %8.4f %8.4f %9.4f\n"
                    "  depth %s %ux%u, frame %ux%u\n",
                    push.proj[0], push.proj[1], push.proj[2], push.proj[3], push.prev_proj[0],
                    push.prev_proj[1], push.prev_proj[2], push.prev_proj[3], current.view[0],
                    current.view[1], current.view[2], current.view[3], current.view[4],
                    current.view[5], current.view[6], current.view[7], current.view[8],
                    current.view[9], current.view[10], current.view[11], m[0], m[1], m[2], m[3],
                    m[4], m[5], m[6], m[7], m[8], m[9], m[10], m[11],
                    vk::to_string(depth_format).c_str(), depth.info.size.width,
                    depth.info.size.height, color.info.size.width, color.info.size.height);
    }
    const vk::DescriptorImageInfo depth_info{.imageView = depth_view,
                                             .imageLayout = vk::ImageLayout::eGeneral};
    const vk::DescriptorImageInfo color_info{.imageView = color_view,
                                             .imageLayout = vk::ImageLayout::eGeneral};
    const auto& prev_frame = *frames[frame_index ^ 1];
    const auto& next_frame = *frames[frame_index];
    frame_index ^= 1;
    const vk::DescriptorBufferInfo prev_info{prev_frame.Handle(), 0, prev_frame.SizeBytes()};
    const vk::DescriptorBufferInfo next_info{next_frame.Handle(), 0, next_frame.SizeBytes()};
    const std::array<vk::WriteDescriptorSet, 4> writes = {{
        {.dstBinding = 0,
         .descriptorCount = 1,
         .descriptorType = vk::DescriptorType::eSampledImage,
         .pImageInfo = &depth_info},
        {.dstBinding = 1,
         .descriptorCount = 1,
         .descriptorType = vk::DescriptorType::eStorageImage,
         .pImageInfo = &color_info},
        {.dstBinding = 2,
         .descriptorCount = 1,
         .descriptorType = vk::DescriptorType::eStorageBuffer,
         .pBufferInfo = &prev_info},
        {.dstBinding = 3,
         .descriptorCount = 1,
         .descriptorType = vk::DescriptorType::eStorageBuffer,
         .pBufferInfo = &next_info},
    }};
    const auto cmdbuf = scheduler.CommandBuffer();
    cmdbuf.bindPipeline(vk::PipelineBindPoint::eCompute, *overlay_pipeline);
    cmdbuf.pushDescriptorSetKHR(vk::PipelineBindPoint::eCompute, *pipeline_layout, 0, writes);
    cmdbuf.pushConstants(*pipeline_layout, vk::ShaderStageFlagBits::eCompute, 0, sizeof(push),
                         &push);
    // The previous frame buffer was written by the last dispatch.
    const vk::MemoryBarrier2 frame_barrier{
        .srcStageMask = vk::PipelineStageFlagBits2::eComputeShader,
        .srcAccessMask = vk::AccessFlagBits2::eShaderWrite,
        .dstStageMask = vk::PipelineStageFlagBits2::eComputeShader,
        .dstAccessMask = vk::AccessFlagBits2::eShaderRead | vk::AccessFlagBits2::eShaderWrite,
    };
    cmdbuf.pipelineBarrier2({.memoryBarrierCount = 1, .pMemoryBarriers = &frame_barrier});
    cmdbuf.dispatch((color.info.size.width + 7) / 8, (color.info.size.height + 7) / 8, 1);

    scheduler.DeferOperation([device, depth_view, color_view] {
        device.destroyImageView(depth_view);
        device.destroyImageView(color_view);
    });
}

} // namespace Vulkan
