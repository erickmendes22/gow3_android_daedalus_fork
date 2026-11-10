#!/usr/bin/env python3
"""Synthetic graphics pipeline bind-elision gate; never presented as measured Mali FPS."""
import random

def execute(actions, enabled):
    cmd = 0
    current = None
    cached_cmd = -1
    cached_pipeline = None
    emitted = 0
    results = []
    for op, value in actions:
        if op == "new":
            cmd += 1
            current = None
            cached_cmd = -1
            cached_pipeline = None
        elif op == "gfx":
            if not enabled or cached_cmd != cmd or cached_pipeline != value:
                emitted += 1
                current = value
                cached_cmd = cmd
                cached_pipeline = value
        elif op == "raw":
            current = value
            cached_cmd = -1
            cached_pipeline = None
        elif op == "compute":
            pass  # Vulkan compute and graphics binds are independent.
        elif op == "draw":
            results.append((cmd, current))
        else:
            raise AssertionError(op)
    return emitted, results

def check(actions):
    old = execute(actions, False)
    new = execute(actions, True)
    assert old[1] == new[1], "bind state diverged"
    assert new[0] <= old[0], "extra binds"
    return old[0], new[0]

if __name__ == "__main__":
    baseline = [("new", 0)]
    for i in range(2800):
        baseline.append(("gfx", 1 + (i // 4) % 128))
        baseline.append(("draw", 0))
    old, new = check(baseline)
    assert (old, new) == (2800, 700), (old, new)
    rng = random.Random(0x720615)
    for _ in range(256):
        events = [("new", 0)]
        for i in range(1200):
            op = rng.choices(["gfx", "raw", "compute", "new", "draw"],
                             weights=[48, 3, 15, 2, 32])[0]
            events.append((op, rng.randrange(100) if op in ("gfx", "raw") else 0))
        check(events)
    print("GOW3_DRAW_BIND_PREFLIGHT synthetic old=%d new=%d saved=%d"
          " randomized_traces=256 equivalence=PASS" % (old, new, old-new))
    print("Synthetic Vulkan command-call counts only, NOT a Mali hardware FPS measurement.")
