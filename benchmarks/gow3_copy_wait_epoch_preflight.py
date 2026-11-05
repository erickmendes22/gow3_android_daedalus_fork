#!/usr/bin/env python3
"""Compile and test the REAL GoW3 copy pool, before and after epoch-bounded waits.

Both modes extract the complete Pool class from Git source; no hand-written
model of the scheduler is benchmarked. Baseline commit is the unchanged
production ref. Uses an adversarial concurrent producer of *later* copies.
NO APK; a positive host result is not a Mali gameplay FPS result.
"""
from pathlib import Path
import subprocess
import tempfile
import re

ROOT = Path(__file__).resolve().parents[1]
FILE = "gpu/shim/gow3_copy.cpp"
BASE_SHA = "0f919000565d556211eeefbf196bb1972fc65084"

HEAD = r"""
#include <algorithm>
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <deque>
#include <functional>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>
namespace Gow3Threads { unsigned Available() { return 4; } }
namespace Common { void SetCurrentThreadName(const char*) {} }
namespace Gow3Copy {
namespace {
thread_local bool in_copy_thread = false;
"""

TAIL = r"""
} // anonymous namespace
void run() {
    setenv("GOW3_COPY_THREADS", "2", 1);
    Pool pool;
    std::atomic<bool> first_done{false};
    std::atomic<bool> later_done{false};
    // Copy issued before the barrier: its completion MUST be observed.
    pool.Async([&] {
        std::this_thread::sleep_for(std::chrono::milliseconds(45));
        first_done.store(true, std::memory_order_release);
    });
    std::thread later([&] {
        std::this_thread::sleep_for(std::chrono::milliseconds(6));
        // This copy is issued AFTER the barrier began. A submission which
        // only needs the first copy must not wait for this future one.
        pool.Async([&] {
            std::this_thread::sleep_for(std::chrono::milliseconds(230));
            later_done.store(true, std::memory_order_release);
        });
    });
    const auto started = std::chrono::steady_clock::now();
    WAIT_CALL;
    const auto ended = std::chrono::steady_clock::now();
    const bool first = first_done.load(std::memory_order_acquire);
    const bool future = later_done.load(std::memory_order_acquire);
    later.join();
    if (!first) std::abort();
    pool.WAIT_METHOD();
    if (!later_done.load(std::memory_order_acquire)) std::abort();
    // Stress asynchronous callback order across closed epochs with multiple
    // workers: a later copy must never publish its completion callback first.
    std::mutex callback_mutex;
    std::vector<int> callback_order;
    pool.Async([&] {
        std::this_thread::sleep_for(std::chrono::milliseconds(18));
    });
    pool.AfterCopies([&] {
        std::scoped_lock lock{callback_mutex};
        callback_order.push_back(1);
    });
    pool.Async([&] {
        std::this_thread::sleep_for(std::chrono::milliseconds(2));
    });
    pool.AfterCopies([&] {
        std::scoped_lock lock{callback_mutex};
        callback_order.push_back(2);
    });
    pool.WAIT_METHOD();
    if (callback_order != std::vector<int>{1, 2}) std::abort();
    // Negative control: the common no-work barrier should not regress.
    const auto empty_started = std::chrono::steady_clock::now();
    for (unsigned i=0; i<60000; ++i) pool.WAIT_METHOD();
    const auto empty_ended = std::chrono::steady_clock::now();
    const auto empty_ns = std::chrono::duration<double,std::nano>(
        empty_ended-empty_started).count()/60000.0;
    // Loaded-but-no-future-producer control: ensure the bounded barrier
    // does not create a large per-submission tax in normal use.
    const auto ordinary_started = std::chrono::steady_clock::now();
    for (unsigned i=0;i<4000;++i) {
        pool.Async([] {});
        pool.WAIT_METHOD();
    }
    const auto ordinary_ended = std::chrono::steady_clock::now();
    const auto ordinary_us = std::chrono::duration<double,std::micro>(
        ordinary_ended-ordinary_started).count()/4000.0;
    std::printf("GOW3_COPY_CONTROL mode=MODE empty_ns=%.3f one_copy_us=%.3f\n",
                empty_ns, ordinary_us);
    std::printf("GOW3_COPY_EPOCH mode=MODE elapsed_ms=%.3f "
                "prefix_done=%d later_done_at_barrier=%d\n",
                std::chrono::duration<double,std::milli>(ended-started).count(),
                int(first), int(future));
}
} // namespace Gow3Copy
int main() { Gow3Copy::run(); }
"""


def extract_pool(text: str) -> str:
    start = text.index("class Pool {")
    stop = text.index("Pool& GetPool()", start)
    actual = text[start:stop]
    if "void AfterCopies(" not in actual or "void Complete(u64 epoch)" not in actual:
        raise ValueError("Expected production Pool epoch and callback semantics not found")
    return actual


def run_mode(text: str, mode: str, temp: Path):
    if mode not in ("baseline", "candidate"):
        raise ValueError("Unknown pool variant")
    symbol = "WaitAll" if mode == "baseline" else "WaitIssued"
    pool = extract_pool(text)
    if f"void {symbol}()" not in pool:
        raise ValueError(f"{symbol} absent from source")
    tail = TAIL.replace("WAIT_CALL",f"pool.{symbol}();").replace(
        "WAIT_METHOD",symbol).replace("MODE",mode)
    filename = temp / f"{mode}.cpp"
    binary = temp / mode
    filename.write_text(HEAD + pool + tail)
    subprocess.run(["c++","-std=c++20","-O2","-pthread","-Wall",
                    "-Wextra","-Werror",str(filename),"-o",str(binary)], check=True)
    output = subprocess.check_output([str(binary)],text=True,timeout=15)
    if "prefix_done=1" not in output:
        raise ValueError("Pre-barrier copy was not completed")
    suffix = re.search(r"later_done_at_barrier=(\d+)",output)
    elapsed = re.search(r"elapsed_ms=([\d.]+)",output)
    control = re.search(r"one_copy_us=([\d.]+)", output)
    if not suffix or not elapsed or not control:
        raise ValueError("Missing benchmark output")
    return float(elapsed.group(1)),int(suffix.group(1)),float(control.group(1)),output.strip()


if __name__ == "__main__":
    baseline = subprocess.check_output(["git","show",f"{BASE_SHA}:{FILE}"],
                                       cwd=ROOT,text=True)
    current = (ROOT/FILE).read_text()
    with tempfile.TemporaryDirectory(prefix="gow3-copy-epoch-") as tmp:
        directory = Path(tmp)
        old_ms, old_future, old_normal_us, old_out = run_mode(baseline,"baseline",directory)
        new_ms, new_future, new_normal_us, new_out = run_mode(current,"candidate",directory)
    print(old_out)
    print(new_out)
    print("HOST PREFLIGHT: confirmed relative reduction",
          f"{old_ms-new_ms:.3f} ms, {old_ms/max(new_ms,0.001):.2f}x wait speedup")
    assert old_future == 1, "Baseline did not include post-barrier task"
    assert new_future == 0, "Candidate still waited for a post-barrier task"
    assert new_ms < old_ms * 0.70, "No substantial wait reduction in synthetic overlap"
    # Avoid CI host jitter while still rejecting the former heap-callback
    # implementation's observed 2.067us -> 3.575us normal-path regression.
    assert new_normal_us <= old_normal_us * 1.5 or new_normal_us - old_normal_us <= 1.0, (
        f"Ordinary one-copy barrier regressed: {old_normal_us:.3f}us -> {new_normal_us:.3f}us")
    print("PASS: pre-barrier copies complete and later copies do not delay the wait.")
    print("LIMITATION: Crafted host concurrency case. Not measured GoW3 PanVK FPS;"
          " requires evidence of late-copy contention before promoting an APK.")
