#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""SotC: make the existing *GPU image readback* diagnostic actually work on Android.

This is NOT a rendering workaround. No shader, format, resource or barrier
semantics are changed. The Android bbgpu glue has a hard-coded
ConsumeImageDumpRequest() == false, so SOTC_DUMP never arms. A bounded,
one-shot delayed request captures the existing volumetric-fog compute stages
and logs exact shader/image/format identities. The diagnostic output is
directed to sotcport/logs/ and included by the existing Export logs action.
"""

from pathlib import Path


def replace_once(text: str, before: str, after: str, label: str) -> str:
    count = text.count(before)
    if count != 1:
        raise ValueError(f"SotC pass capture {label}: expected one anchor, got {count}")
    return text.replace(before, after, 1)


def stage_pass_capture(gpu: Path) -> None:
    shim = gpu / "shim/bbgpu.cpp"
    text = shim.read_text()
    text = replace_once(
        text,
        "bool ConsumeImageDumpRequest() { return false; } // sotc: SOTC_DUMP needs RenderDoc hooks",
        r'''// Android has no RenderDoc/F12 hook. The previous constant-false stub made
// SOTC_DUMP permanently unreachable on a real device. Arm it once after a
// configured amount of actual GPU command processing time. Do not modify
// frames, shader code, graphics flags, or the game's presentation.
bool ConsumeImageDumpRequest() {
    const char* after = std::getenv("SOTC_AUTO_GPU_DUMP_AFTER");
    if (!after || !*after || after[0] == '0') return false;
    static const auto start = std::chrono::steady_clock::now();
    static bool issued = false;
    if (issued) return false;
    const auto seconds = std::clamp(std::atoi(after), 10, 300);
    if (std::chrono::steady_clock::now() - start < std::chrono::seconds(seconds)) {
        return false;
    }
    issued = true;
    std::fprintf(stderr, "SOTC GPU PASS CAPTURE armed (after %d s)\n", seconds);
    return true;
}''',
        "replace permanently inert Android GPU dump request")
    shim.write_text(text)

    cpp = gpu / "shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp"
    text = cpp.read_text()
    text = replace_once(
        text,
        "    static u32 session = 0;\n    static u32 seq = 0;\n    if (targets.empty()) {",
        "    static u32 session = 0;\n    static u32 seq = 0;\n"
        "    static u64 total_bytes = 0;\n"
        "    if (targets.empty()) {",
        "track total scheduled dump bytes")
    text = replace_once(
        text,
        '''        pending = targets;
        dir = Common::FS::GetUserPath(Common::FS::PathType::LogDir) / fmt::format("dump_{}", ++session);
        std::filesystem::create_directories(dir);
        seq = 0;''',
        r'''        pending = targets;
        const char* requested = std::getenv("SOTC_GPU_DUMP_DIR");
        const auto base_dir = requested && *requested
                                  ? std::filesystem::path{requested}
                                  : Common::FS::GetUserPath(Common::FS::PathType::LogDir);
        dir = base_dir / fmt::format("dump_{}", ++session);
        std::filesystem::create_directories(dir);
        seq = 0;
        total_bytes = 0;
        std::fprintf(stderr,
                     "SOTC GPU PASS CAPTURE started: dir=%s, frame=%llu, "
                     "targets=%zu, cap=64 MiB\n",
                     dir.string().c_str(),
                     static_cast<unsigned long long>(
                         SotcStats::flip_count.load(std::memory_order_relaxed)),
                     pending.size());''',
        "write captures into the user-exportable Android logs directory")
    text = replace_once(
        text,
        '''    pending.erase(it);
    std::vector<VideoCore::ImageId> seen;
    u32 index = 0;
    for (const auto image_id : bound_images) {
        if (!image_id || std::find(seen.begin(), seen.end(), image_id) != seen.end()) {
            continue;
        }
        seen.push_back(image_id);
        texture_cache.DumpImage(image_id, dir / fmt::format("{:02}_cs_{:08x}_img{}", seq, pgm_hash,
                                                             index++));
    }
    ++seq;''',
        r'''    pending.erase(it);
    std::vector<VideoCore::ImageId> seen;
    u32 index = 0;
    std::fprintf(stderr, "SOTC GPU PASS CAPTURE stage=%#llx frame=%llu bound=%zu\n",
                 static_cast<unsigned long long>(pgm_hash),
                 static_cast<unsigned long long>(
                     SotcStats::flip_count.load(std::memory_order_relaxed)),
                 bound_images.size());
    for (const auto image_id : bound_images) {
        if (!image_id || std::find(seen.begin(), seen.end(), image_id) != seen.end()) {
            continue;
        }
        seen.push_back(image_id);
        const auto& image = texture_cache.GetImage(image_id);
        // Avoid staging unsupported depth/stencil images on Adreno. Volumetric
        // fog reads/writes color images, which are the useful evidence here.
        const auto& info = image.info;
        const u64 texel = std::max(1u, info.num_bits / 8);
        const u64 bytes = u64{info.size.width} * info.size.height * info.size.depth *
                          info.resources.layers * texel;
        const bool eligible = !info.props.is_depth && bytes > 0 &&
                              bytes <= 16_MB && total_bytes + bytes <= 64_MB;
        std::fprintf(stderr,
                     "SOTC GPU PASS CAPTURE image shader=%#llx idx=%u "
                     "addr=%#llx %ux%ux%ux%u fmt=%s bytes=%llu "
                     "storage=%d render=%d depth=%d action=%s\n",
                     static_cast<unsigned long long>(pgm_hash), index,
                     static_cast<unsigned long long>(info.guest_address),
                     info.size.width, info.size.height, info.size.depth,
                     info.resources.layers,
                     vk::to_string(info.pixel_format).c_str(),
                     static_cast<unsigned long long>(bytes),
                     int(image.usage.storage), int(image.usage.render_target),
                     int(image.usage.depth_target),
                     eligible ? "dump" : "skip");
        if (eligible) {
            total_bytes += bytes;
            texture_cache.DumpImage(image_id,
                dir / fmt::format("{:02}_cs_{:08x}_img{}", seq, pgm_hash, index));
        }
        ++index;
    }
    ++seq;
    if (pending.empty()) {
        std::fprintf(stderr,
                     "SOTC GPU PASS CAPTURE all requested compute stages visited; "
                     "scheduled=%llu bytes, dir=%s\n",
                     static_cast<unsigned long long>(total_bytes),
                     dir.string().c_str());
    }''',
        "bounded per-shader pre/post-fog image captures")
    cpp.write_text(text)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--gpu", required=True, type=Path)
    args = parser.parse_args()
    stage_pass_capture(args.gpu)
