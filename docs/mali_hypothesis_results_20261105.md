# GoW3 Android Mali — Tested optimization hypotheses (2026-11-05)

**Scope:** Analysis branch only. No APK produced; no production renderer code changed.
Production branch: fix/gow3-218-panvk-videoout-label-retire-20261031.

## Grounded observations

- G615 MC6 at 1280x720: previous session measured ~7.0–7.4 steady FPS, including intervals without new pipelines or image allocations.
- Existing checked-in fixture from GodOfWar3-Logs-20261105-152530.zip: sampled Rasterizer::Draw CPU 22.38 ms/frame, of which pipeline lookup 7.56 ms/frame and all other draw CPU 14.82 ms/frame.
- Mali G720 is a separate run, with graphics_pipeline_new=109/4347.10/39.88/57.98; this explains potential stutter spikes, not the G615 no-compile steady FPS.
- Draw CPU samples are estimated wall-clock host work. GPU stages and true critical path have not been measured in the G615 capture.

## GitHub Actions tests (2026-11-05)

1. Image-free draws: existing true A/B *host synthetic* microbench repeated; old 3.017 ns/draw, new 2.181 ns/draw; optimistic 0.000386 ms/frame using 462 draws/frame. REJECT: negligible, 10 ms/frame build gate blocks APK.
2. Pipeline cache lifecycle: added actual Vulkan (host driver) compute pipeline test. Distinct live and worker caches compile successfully, worker-to-live merge and snapshot restore work, and private-worker pre-seeding can be executed. The host llvmpipe driver serializes 32 bytes (header only, has_cache_payload=0); no evidence of actual compiled shader reuse or PanVK speedup. Do not promote this to an APK.
3. Frame budget: added four Python tests and explicit theoretical upper bounds for saving an entire stage on the frame's critical path. At 7.4 FPS:

| Removed stage | Entire stage ms/frame | Theoretical maximum FPS | Max gain |
|---|---:|---:|---:|
| Pipeline lookup | 7.56 | 7.839 | 5.93% |
| Other Draw CPU | 14.82 | 8.312 | 12.32% |
| All sampled Draw CPU | 22.38 | 8.869 | 19.85% |

To gain 25% at 7.4 FPS requires at least 27.03 ms/frame of critical-path savings. The entire sampled Draw CPU work is only 22.38 ms/frame, so CPU draw micro-optimizations cannot on their own explain or solve the sustained 7 FPS problem. The above are optimistic mathematical upper bounds, NOT predicted FPS improvements.

## Decisions

- Discard image-free texture bookkeeping optimization; no APK.
- Keep pipeline cache warmup as separate cold-stutter research; do not claim it fixes steady FPS.
- Do not add speculative pipeline worker-cache seeding in production: host driver gives no compiled cache payload and current test does not demonstrate gains on PanVK.
- Next high-impact issue is attributing the remaining ~135 ms/frame. The renderer already has an optional Vulkan timestamp profiler in gpu/shadps4/video_core/renderer_vulkan/vk_gpu_profiler.cpp (GOW3_GPU_PROFILE=1), but GPU execution timing is missing for these G615 logs. Need correlated FEX/PM4, Vulkan queue GPU timestamps, and VideoOut waits before a claim of a substantial steady-state FPS optimization.
- Preserve existing 10 ms/frame synthetic gate on APK production branch.

## Reproduction

Run the test workflow:
https://github.com/erickmendes22/gow3_android_daedalus_fork/actions/runs/42016088828

Relevant files:
- benchmarks/mali_pipeline_cache_lifecycle.cpp
- benchmarks/mali_frame_budget_gate.py
- tests/test_mali_frame_budget_gate.py
- benchmarks/mali_draw_perf_gate.py
- .github/workflows/gow3-mali-pipeline-preflight.yml

This test environment uses llvmpipe graphics software on an x86 CI runner and does not benchmark Mali GPU hardware or GoW3 Vulkan graphics pipelines.

## 2026-11-05 follow-up: real source PM4 and copy-pool tests

### PM4 register checksum condition (correctness)

Production previously tested whether the `DrawPreparation*` object existed,
even when `DrawPreparation::Enabled()` was false because no preparation
workers were running. Its register-packet hash was therefore still computed
without a consumer on Mali with `GOW3_PREP_WORKERS=0`.

The analysis-branch correction changes the guard to
`(draw_prep && draw_prep->Enabled()) || force_checksum` while preserving
the explicit `GOW3_PM4_CHECKSUM_ALWAYS` rollback.

A native host benchmark compiles the exact `Liverpool::HashRegisterPacket`
body extracted from the project's source. At 64 words/packet, savings were
approximately 90-120 ns/packet on the Actions x86 host. At that rate,
saving 10 ms/frame would require about 83,000-109,000 such packets per frame.
The G615 fixture does not include measured packet counts; **do not claim a
material device FPS gain from this correction alone**. The legacy checksum
and dirty-register tests are included in the no-APK CI.

### Copy-pool wait: actual synchronization change and two workload controls

In the original `gpu/shim/gow3_copy.cpp`,
`Gow3Copy::WaitAsync()` called `Pool::WaitAll()`: this waited until
**all** globally pending copies finished, even copies enqueued on another
producer thread **after** the barrier. A GPU submission only needs the
prefix issued before its barrier.

The analysis branch implements `Pool::WaitIssued()`, which:
- Under the existing pool mutex, closes the issued prefix as an epoch;
- Helps execute only queued tasks whose epoch belongs to the required prefix;
- Awaits a release/acquire `retired_epoch` watermark, published by `Complete`
  **after** all callbacks for retired epochs run;
- Does not wait for unrelated future copies or allocate a callback per wait;
- Leaves `AfterCopies` callback ordering and `GOW3_COPY_THREADS` unchanged.

The regression benchmark extracts and compiles the **real Pool class** twice:
the original source from production commit `0f919000` and the candidate
branch's source. Results on the GitHub Actions x86 host:

| Scenario | Original | Candidate | Meaning |
|---|---:|---:|---|
| Deliberately overlapping **late producer** | 236.142 ms | 45.032 ms | 191.110 ms less waiting; prefix and callback order verified |
| Ordinary one-copy barrier | 2.147 µs | 2.150 µs | No meaningful normal-path regression in this run |
| Empty barrier | 13.844 ns | 9.270 ns | No added empty-barrier overhead in this run |

These are controlled host tests, not GoW3 game FPS tests. A late concurrent
producer is **required** for the large 191 ms benefit; its frequency and
critical-path contribution have not been established in the G615 device logs.
The existence of multiple copy-issuing call sites in `buffer_cache.cpp`
proves this scenario is possible, not common or costly in real gameplay.

**Decision:** Keep both code changes isolated in
`analysis/gow3-mali-pipeline-preflight-20261105`. Do not generate an APK
or claim an FPS uplift until device evidence attributes significant recurring
wait time to the copy-pool's later tasks. The original native/APK production
branch is unchanged, and the 10 ms/frame gate remains intact.

Copy-pool and PM4 test run (no APK):
https://github.com/erickmendes22/gow3_android_daedalus_fork/actions/runs/42019263894

## Follow-up: four **actual** G615 steady-state log intervals and new PM4 hypothesis

After finding the original uploaded ZIP in the Library, the source fixture was
reconstructed from the real `GodOfWar3-Logs-20261105-152530.zip` rather than
from a synthetic workload. Original source SHA-256:
`9ca4977665a27011cc9bcb5977d4cb309649909c9a816cb96ce443b62e9cf97f`.
The four consecutive no-new-pipeline/no-image-allocation intervals (35,724 ms
wall total, estimated 256 delivered frames) give approximately **7.166 FPS**
and **139.547 ms/frame**; the frame count is inferred from prepare samples
(1/32), not an exact display-frame counter.

| Stage | Estimated ms/frame | Important interpretation |
|---|---:|---|
| `pm4_submit_wall` | 56.219 | Sampled wall time, can include nested ProcessGraphics and coroutine suspension |
| `gpu_draw_cpu` | 22.380 | Inside PM4 wall in part; do NOT add to PM4 |
| `pipeline_lookup` | 7.560 | Subset of draw CPU; even perfect elimination <10 ms/frame |
| `submit_host_copy_wait` | 0.098 | Entire stage far below 10 ms/frame |
| `submit_throttle` | 0.041 | Every throttle is counted, no 1/32 multiplier |
| `fence_wait` | 2.050 | Host fence stall, not necessarily pure GPU work |
| `ahb_total` | 6.331 | Sampled CPU presentation |
| `submit_mutex` | 1.909 | Includes one isolated 15.24 ms sampled spike; not proof of persistent 1.9 ms contention |

See `benchmarks/fixtures/mali_g615_steady_intervals_20261105.json`,
`benchmarks/mali_steady_state_cost_gate.py`, and
`tests/test_mali_steady_state_cost_gate.py`. The no-APK workflow now
**rejects** a proposal predicated on a 10 ms/frame improvement from eliminating
copy waits or timeline throttle alone.

### Safety changes from real device metrics

- `GOW3_MALI_COPY_EPOCH_WAIT=1` now required to enable the epoch-bounded
  wait experiment; original `Pool::WaitAll` is the **default**. Host
  one-copy timing proved noisy across runs (including a regression).
- `GOW3_MALI_DIRECT_TIMELINE_WAIT=1` now required for the alternative
  timeline-semaphore wait; original refresh is the **default**. The real
  `submit_throttle` budget is only 0.041 ms/frame, and host Vulkan
  already-signaled timing varied between benchmark executions.
- Both are unproven for significant Mali game FPS and remain analysis-only.

### New PM4 blocked-coroutine CPU occupancy test

`Liverpool::Process` resumes a guest PM4 fiber in a loop. A `WaitRegMem`,
`MemSemaphore`, or `Rewind` operation can repeatedly `co_yield` while its
condition is unresolved. With no other runnable guest submit or command, the
resuming thread can busy-spin while the producer still needs CPU.

A deliberately **opt-in** analysis-only experiment tags exactly those blocked
PM4 coroutine yield states and, only when `num_submits==1`,
`num_commands==0`, and Mali PanVK is active, permits a short backoff
through `GOW3_MALI_PM4_IDLE_BACKOFF_US=1..100`; the variable is **unset**
by default, and draws, fulfilled waits and concurrent-submit cases retain
their old behavior.

`benchmarks/gow3_pm4_idle_coroutine_gate.py` compiles Liverpool's actual
C++ Task coroutine structure and models the scheduler with a 35 ms blocked
condition, then checks per-thread CPU clock as well as wall clock:

| Host blocked-coroutine synthetic | Baseline | Candidate 20µs |
|---|---:|---:|
| CPU occupancy for 35 ms blocked wait | 35.086 ms | 2.341 ms |
| Elapsed wall-clock waiting | 35.081 ms | 35.109 ms |
| Resume count | 17,951,256 | 458 |
| Release-to-resume delay | 0.002 ms | 0.039 ms |
| Other runnable submit | unthrottled | unthrottled |

The approximately **32.745 ms saved are CPU occupancy in an intentionally
blocked 35 ms test**, **not removed frame time**. Actual G615 logs do not
contain per-opcode blocked-yield counts or an isolated GPU command-thread
CPU-time breakdown, so we cannot infer how often the test scenario occurs
or claim game FPS gain. This is why the branch remains experimental and
no APK was generated.

The full native no-APK preflight workflow with original code, negative
controls, actual G615 sample-factor gates, the Vulkan timeline API experiment,
and the PM4 coroutine experiment:
https://github.com/erickmendes22/gow3_android_daedalus_fork/actions/runs/42026758570

**Next decision criterion:** prioritize a measured change that reduces an
observed recurring >=10 ms/frame component, not a large percentage on
an unobserved synthetic case. For PM4, a material claim requires evidence
of the blocked wait opcode frequency AND per-thread CPU-clock usage; wall
time alone confounds nested coroutines, GPU waits, and CPU work.

## Decision update: **tester APK justified by host producer-contention A/B**

The earlier requirement for real-device blocked-opcode counts *before* packaging
was too strict and is **superseded**. Real-device FPS confirmation is the role
of the testers **after** a successful native build. A host gate should show
a significant **wall-time improvement on representative work contention**,
not merely a CPU utilization percentage.

`benchmarks/gow3_pm4_contended_producer_gate.py` now compiles the actual
`Liverpool::Task` coroutine type, forces the PM4 consumer and a FEX-like
producer to run on **one pinned CPU core**, and measures five independent A/B
pairs with the **same 35 ms of useful CPU work**.

Locally on x86 Linux:

| Median from 5 paired runs | Original busy-spin | 20µs blocked-only backoff |
|---|---:|---:|
| Time to producer completion | 71.1 ms | 40.0 ms |
| CPU used by PM4 consumer | 35.9 ms | 4.9 ms |
| Useful producer CPU work | 35 ms | 35 ms |

The change saves **~31.1 ms of measured wall-clock delay (43.7%)**
under a single-core CPU-contention scenario; it is NOT a measured GoW3
per-frame improvement and does not imply +43.7% FPS on Android. Unlike the
former 35 ms sleeping-producer test, it demonstrates that releasing a core
**can accelerate the thread that completes the guest wait**.

Production guard: only a blocked PM4 `WaitRegMem`/`Rewind`/`MemSemaphore`
coroutine, with one pending submit and no other ready command, may back off.
The isolated PanVK launcher defaults `GOW3_MALI_PM4_IDLE_BACKOFF_US=20`,
with `=0` to disable. Non-PanVK drivers are unaffected. Both the
experimental copy-pool epoch wait and direct Vulkan timeline wait remain
disabled by default after their device cost ceilings were found too small.

The original production branch is unchanged. A **separately installable**
diagnostic APK workflow was started on this analysis branch to allow
testers to evaluate the real G615/G720 impact only once its native
compile, release packaging, and signing checks complete:
https://github.com/erickmendes22/gow3_android_daedalus_fork/actions/runs/42028939625

If successful, tester comparison should use matched scene, same resolution
and settings, with FPS and correct rendering. An isolated benchmark is a
reason to **test**, not a claim of achieved device FPS.
