#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""SotC-only draw-completeness backport to the *staged* original GPU renderer.

Applied after stage_sotc_stage_spec_cpu, so that the native Android APK
contains the correction. Never replace the fully staged pipeline-cache file:
that would delete the earlier shader-specialization performance work.
"""
from pathlib import Path

def once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"SotC complete-draw source drift {label}: {count}")
    return source.replace(old, new, 1)

def patch_sotc_complete_draws(gpu: Path) -> None:
    path = Path(gpu) / "shadps4/video_core/renderer_vulkan/vk_pipeline_cache.cpp"
    source = path.read_text()
    source = once(source, "void PipelineCache::PublishShaders(bool wait) {",
'''// Only the Shadow of the Colossus Android launcher enables this guard.
// Draws must not be dropped while async graphics work is outstanding.
static bool SotcRequireCompleteDraws() {
    const char* value = std::getenv("SOTC_NO_DROPPED_DRAWS");
    return value && value[0] == '1' && value[1] == 0;
}

void PipelineCache::PublishShaders(bool wait) {''',
"isolated gate")

    source = once(source,
'''        ++g_gow3_pending_draws;
        return nullptr;
    }
    const auto [it, is_new] = graphics_pipelines.try_emplace(sel.graphics_key);''',
'''        // SotC: await the requested pipeline, not the whole compiler queue.
        // When the queue was full, fall through to the synchronous path.
        if (SotcRequireCompleteDraws()) {
            const auto waiting = pending_graphics.find(sel.graphics_key);
            if (waiting != pending_graphics.end()) {
                {
                    PhaseTimer timer{g_gow3_compile_wait_ns};
                    waiting.value()->job.Wait();
                }
                PublishGraphics();
                const auto ready = graphics_pipelines.find(sel.graphics_key);
                if (ready != graphics_pipelines.end()) {
                    return ready->second.get();
                }
                // Actual compiler failure: cannot submit a valid draw.
                return nullptr;
            }
        } else {
            ++g_gow3_pending_draws;
            return nullptr;
        }
    }
    const auto [it, is_new] = graphics_pipelines.try_emplace(sel.graphics_key);''',
"no drop on pending graphics")

    source = once(source,
'''    const bool compile_async = AsyncCompilation() && hw_stage != HwStage::Compute &&
                               !sel.regs->stage_enable.hs_en &&
                               !EmulatorSettings.IsShaderCollect();''',
'''    // Materialize first-use shaders synchronously for SotC. Graphics pipeline
    // creation can still run on the worker, but is awaited at the draw.
    const bool compile_async = AsyncCompilation() && hw_stage != HwStage::Compute &&
                               !sel.regs->stage_enable.hs_en &&
                               !EmulatorSettings.IsShaderCollect() &&
                               !SotcRequireCompleteDraws();''',
"first-use shader availability")
    for needle in ("SOTC_STAGE_SPEC_MEMO", "PublishGraphics();",
                   "waiting.value()->job.Wait();", "SotcRequireCompleteDraws()"):
        if needle not in source:
            raise ValueError("Missing expected staged invariant: " + needle)
    path.write_text(source)
    print("PASS SotC complete drawings: no async pending-draw skip; existing memos preserved")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--gpu", required=True, type=Path)
    patch_sotc_complete_draws(parser.parse_args().gpu)
