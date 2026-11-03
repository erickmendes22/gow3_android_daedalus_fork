#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Prevent skipped SotC draws in the actual AjncSystem-based Android renderer.

Run AFTER all other native renderer patches. This source differs from
GoW3's PipelineCache: it has async_workers/QueueAsyncPipeline, not
pending_graphics. Guard source anchors to prevent silently editing wrong code.
"""
from pathlib import Path

def replace_once(src: str, old: str, new: str, label: str) -> str:
    n = src.count(old)
    if n != 1:
        raise ValueError(f"SotC draw-completeness source drift: {label}: {n}")
    return src.replace(old, new, 1)

def patch_sotc_complete_draws(gpu: Path) -> None:
    target = Path(gpu) / "shadps4/video_core/renderer_vulkan/vk_pipeline_cache.cpp"
    s = target.read_text()

    marker = "// sotc: SOTC_ASYNC_SHADERS=0 builds every graphics pipeline"
    gate = '''// Scoped to the SotC Android launcher. Synchronous first-use draws always
// preserve visible geometry even if asynchronous pipeline mode is selected.
static bool SotcRequireCompleteDraws() {
    const char* v = std::getenv("SOTC_NO_DROPPED_DRAWS");
    return v && v[0] == '1' && v[1] == 0;
}

'''
    s = replace_once(s, marker, gate + marker, "isolated SotC-only switch")
    s = replace_once(s,
'''    async_translate_ok = !async_workers.empty() && AsyncTranslateEnabled() &&''',
'''    async_translate_ok = !SotcRequireCompleteDraws() &&
                         !async_workers.empty() && AsyncTranslateEnabled() &&''',
"prevent shader-translation draw skipping")
    s = replace_once(s,
'''    if (queued && liverpool->regs.num_indices > 6) {
        return nullptr;
    }''',
'''    // Do not discard already-submitted geometry just because its pipeline
    // is queued. The existing tiny-draw path already compiles a duplicate
    // synchronously and the worker's later copy is discarded safely.
    if (queued && liverpool->regs.num_indices > 6 &&
        !SotcRequireCompleteDraws()) {
        return nullptr;
    }''',
"pending graphics queue")
    s = replace_once(s,
'''        if (!async_workers.empty() && !tiny_draw && eligible && !queued) {''',
'''        if (!SotcRequireCompleteDraws() &&
            !async_workers.empty() && !tiny_draw && eligible && !queued) {''',
"first-use graphics pipeline")
    for needle in ("SOTC_STAGE_SPEC_MEMO", "SOTC_NO_DROPPED_DRAWS",
                   "QueueAsyncPipeline(pipeline_hash)",
                   "const bool queued = !is_new && !it->second;"):
        if needle not in s:
            raise ValueError(f"Staged original SotC invariant missing: {needle}")
    target.write_text(s)
    print("PASS: original SotC staged renderer draws never skipped for pending async shaders/pipelines")

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--gpu", required=True, type=Path)
    patch_sotc_complete_draws(p.parse_args().gpu)
