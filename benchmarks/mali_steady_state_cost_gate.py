#!/usr/bin/env python3
"""Measured-by-device, sample-correct GoW3 Mali pre-APK cost budget.

These estimates are NOT GPU timestamps and stages may overlap / nest.
Optimistic budget means impossibility to gain 10 ms from smaller stages;
passing the budget does not prove a candidate has saved anything.
"""
import argparse
import json
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent / "fixtures/mali_g615_steady_intervals_20261105.json"

def load():
    return json.loads(FIXTURE.read_text())

def calculate(f):
    fields=f["fields"]
    sums={name:{"samples":0,"sampled_total_ms":0.0} for name in fields}
    elapsed=sum(row["interval_ms"] for row in f["intervals"])
    total_frames=0
    for row in f["intervals"]:
        stages=dict(zip(fields,row["values"]))
        total_frames+=stages["prepare"][0]*f["sample_factors"]["prepare"]
        for key,(count,ms) in stages.items():
            sums[key]["samples"]+=count
            sums[key]["sampled_total_ms"]+=ms
    if total_frames<=0 or elapsed<=0:
        raise ValueError("No frames observed")
    output={"approx_frames":total_frames,"interval_wall_ms":elapsed,
            "approx_fps":total_frames*1000.0/elapsed,
            "frame_budget_ms":elapsed/total_frames,"stages":{}}
    for k,v in sums.items():
        samples=v["samples"]
        total=v["sampled_total_ms"]
        sample_factor=f["sample_factors"][k]
        output["stages"][k]={
            "samples":samples,"sampled_total_ms":total,
            "estimated_ms_per_frame":total*sample_factor/total_frames}
    return output

def optimistic_effect(budget,cost_ms,removed_fraction=1.0):
    if not 0<=removed_fraction<=1:raise ValueError("Fraction out of range")
    saving=cost_ms*removed_fraction
    if saving>=budget["frame_budget_ms"]:return float("inf")
    return 1000.0/(budget["frame_budget_ms"]-saving)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--stage",default=None,help="Hypothesis stage to test")
    parser.add_argument("--fraction",type=float,default=1.0)
    parser.add_argument("--min-ms",type=float,default=10.0)
    parser.add_argument("--report-only",action="store_true")
    args=parser.parse_args()
    f=load();d=calculate(f)
    print(f"DEVICE G615 steady={d['approx_fps']:.3f}fps, "
          f"frame={d['frame_budget_ms']:.3f}ms, "
          f"estimated_frames={d['approx_frames']}, interval_ms={d['interval_wall_ms']}")
    for name in ["pm4_submit_wall","gpu_draw_cpu","pipeline_lookup",
                 "submit_throttle","submit_host_copy_wait","fence_wait",
                 "ahb_total","submit_mutex","submit_vk_queue"]:
        v=d["stages"][name]
        print(f"{name} estimated={v['estimated_ms_per_frame']:.4f}ms/frame "
              f"sampled_total={v['sampled_total_ms']:.2f}ms samples={v['samples']}")
    stage=args.stage
    if stage:
        if stage not in d["stages"]:parser.error("Unknown stage")
        candidate=d["stages"][stage]["estimated_ms_per_frame"]*args.fraction
        best=optimistic_effect(d,candidate)
        print(f"STAGE_GUARD {stage} fraction={args.fraction:.3f} "
              f"best_possible_saved={candidate:.4f}ms/frame "
              f"optimistic_fps={best:.3f}")
        if candidate<args.min_ms and not args.report_only:
            print(f"REJECT: even removing this fraction cannot save {args.min_ms:.2f}ms/frame")
            raise SystemExit(1)
        if candidate>=args.min_ms:
            print("BUDGET PASSED only: must demonstrate this much removed work and correctness")
    print("WARNING: PM4 wall includes draw CPU and coroutine suspension; "
          "stage estimates are not independent or critical-path proof.")

if __name__=="__main__": main()
