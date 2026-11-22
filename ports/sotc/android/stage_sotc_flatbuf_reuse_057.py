#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""SotC ARM64 Android: reuse identical flat UBO bytes inside a live Vulkan tick.

The expensive BindBuffers path writes the same shader SRT flat buffer for many
of SotC's thousands of indexed indirect draws per frame. All guest SRT reads,
resource binds, barriers, and draw calls still execute. This optimization
deduplicates ONLY the host StreamBuffer::Copy of an EXACT BYTE-EQUAL block,
never a guest GPU readback. StreamBuffer wrap generation, command-buffer tick
and VkBuffer handle are part of the key; no old GPU data can be reused.
"""
from pathlib import Path

ORIGINAL = "                const u64 offset = vk_buffer.Copy(flat, ubo_size, alignment);"
REPLACEMENT = r"""                // SotC 0.1.57: do not write an identical immutable UBO
                // repeatedly during one Vulkan command-buffer tick.
                // Every dynamic SRT, guest memory lookup, descriptor and
                // pipeline is still refreshed by the normal BindResources.
#if defined(__ANDROID__) && defined(__aarch64__)
                struct SotcFlatbufCacheLine {
                    std::vector<u32> contents{};
                    vk::Buffer handle{};
                    u64 tick{};
                    u64 generation{};
                    u64 offset{};
                    bool valid{};
                };
                static thread_local std::array<SotcFlatbufCacheLine, 8> sotc_flatbuf_cache{};
                static thread_local size_t sotc_flatbuf_next{};
                static thread_local u64 sotc_flatbuf_queries{};
                static thread_local u64 sotc_flatbuf_hits{};
                static const bool sotc_flatbuf_reuse = [] {
                    const char* v = std::getenv("SOTC_FLATBUF_REUSE");
                    return !v || v[0] != '0';
                }();
                const bool memo_eligible =
                    sotc_flatbuf_reuse && ubo_size >= 128 && ubo_size <= 8192 &&
                    (ubo_size % sizeof(u32)) == 0;
                // The RedMagic trace measured only 4-5% reuse late in play.
                // At that rate an 8-line lookup plus an extra vector copy
                // for every miss can cost more CPU than copies it saves.
                // Every 32768 eligible UBOs, probe 4096 with exact byte
                // checks. If fewer than 6% reuse, bypass the memo for the
                // remaining 28672. The mandatory vk_buffer.Copy still runs.
                static const bool sotc_flatbuf_adaptive = [] {
                    const char* v = std::getenv("SOTC_FLATBUF_ADAPTIVE");
                    return !v || v[0] != '0';
                }();
                static thread_local u64 sotc_probe_queries{};
                static thread_local u64 sotc_probe_hits{};
                static thread_local bool sotc_probe_enabled{true};
                if (memo_eligible && sotc_flatbuf_adaptive) {
                    const u64 position = sotc_probe_queries++ & 32767ULL;
                    if (position == 0) {
                        sotc_probe_enabled = true;
                        sotc_probe_hits = 0;
                    } else if (position == 4096) {
                        sotc_probe_enabled = sotc_probe_hits * 100 >= 4096ULL * 6;
                    }
                }
                const bool memo_lookup = memo_eligible &&
                    (!sotc_flatbuf_adaptive || sotc_probe_enabled);
                const u64 sotc_current_tick = scheduler.CurrentTick();
                const u64 sotc_current_wrap = vk_buffer.WrapGeneration();
                const vk::Buffer sotc_current_handle = vk_buffer.Handle();
                u64 offset{};
                bool memo_hit = false;
                if (memo_lookup) {
                    for (const auto& line : sotc_flatbuf_cache) {
                        if (line.valid && line.tick == sotc_current_tick &&
                            line.generation == sotc_current_wrap &&
                            line.handle == sotc_current_handle &&
                            line.contents.size() * sizeof(u32) == ubo_size &&
                            std::memcmp(line.contents.data(), flat, ubo_size) == 0) {
                            offset = line.offset;
                            memo_hit = true;
                            break;
                        }
                    }
                }
                if (!memo_hit) {
                    offset = vk_buffer.Copy(flat, ubo_size, alignment);
                    if (memo_lookup) {
                        auto& slot = sotc_flatbuf_cache[
                            sotc_flatbuf_next++ % sotc_flatbuf_cache.size()];
                        slot.contents.assign(flat, flat + ubo_size / sizeof(u32));
                        slot.handle = vk_buffer.Handle();
                        slot.tick = scheduler.CurrentTick();
                        slot.generation = vk_buffer.WrapGeneration();
                        slot.offset = offset;
                        slot.valid = true;
                    }
                }
                if (memo_hit && sotc_flatbuf_adaptive) {
                    ++sotc_probe_hits;
                }
                if (SotcStats::kFpsLog && memo_eligible) {
                    ++sotc_flatbuf_queries;
                    sotc_flatbuf_hits += memo_hit;
                    if ((sotc_flatbuf_queries % 16384) == 0) {
                        std::fprintf(stderr,
                            "SOTC FLATBUF REUSE: %llu/%llu copies avoided (%.1f%%), wrap=%llu\n",
                            static_cast<unsigned long long>(sotc_flatbuf_hits),
                            static_cast<unsigned long long>(sotc_flatbuf_queries),
                            100.0 * double(sotc_flatbuf_hits) / double(sotc_flatbuf_queries),
                            static_cast<unsigned long long>(vk_buffer.WrapGeneration()));
                    }
                }
#else
                const u64 offset = vk_buffer.Copy(flat, ubo_size, alignment);
#endif"""

def patch(gpu: Path) -> None:
    path = gpu / "shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp"
    source = path.read_text()
    if "SOTC FLATBUF REUSE:" in source:
        raise ValueError("SotC Flatbuf: pinned Vulkan UBO copy changed (already patched)")
    if source.count(ORIGINAL) != 1:
        raise ValueError("SotC Flatbuf: pinned Vulkan UBO copy changed")
    for required in (
        "SotcPerf::BindGraphicsPipeline",
        "const u32 ubo_size = stage.FlatBuf().size() * sizeof(u32);",
        "buffer_infos.emplace_back(vk_buffer.Handle(), offset, ubo_size);",
    ):
        if required not in source:
            raise ValueError("SotC Flatbuf: missing existing renderer safeguard " + required)
    # The PC 0.74 depth/G-buffer fastpaths supersede the pre-0.74
    # experimental SOTC_RT_MEMO. Do not require a removed marker.
    if "DepthFastBeginCheck" not in source and "SOTC_RT_MEMO" not in source:
        raise ValueError("SotC Flatbuf: neither PC exact fastpath nor legacy RT memo found")
    source = source.replace(ORIGINAL, REPLACEMENT)
    path.write_text(source)
    print("SotC ARM64: exact UBO de-duplication per tick, handle and wrap; no GPU readback or guest draw skipped")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gpu", required=True, type=Path)
    patch(parser.parse_args().gpu)
