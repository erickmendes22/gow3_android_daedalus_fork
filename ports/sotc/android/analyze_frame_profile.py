#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Extract REAL Android SotC per-frame bottleneck measurements from a log ZIP.

The prior Android logs contain only '[PERF] Last minute' and a few compiler
warnings; they cannot identify the sustained frame bottleneck. Run with
the 0.1.27 "CPU/GPU frame bottleneck profiling" option enabled and analyze
the resulting zipped Android logs. Values are CPU time or CPU wait time,
NOT direct GPU execution timings. No FPS uplift is claimed from diagnostics.
"""
import argparse
from collections import defaultdict
from pathlib import Path
import re
from zipfile import ZipFile


SPLIT = re.compile(r'SOTC DRAW SPLIT per frame \((\d+) frames\):\s*(.*)')
FPS = re.compile(r'SOTC FPS ([0-9.]+) at ([0-9.]+)s;')
FRAME = re.compile(r'SOTC FRAMES p50 ([0-9.]+) ms, p99 ([0-9.]+) ms .*')
OLD = re.compile(r'\[PERF\s*\] Last minute:\s*([0-9.]+) FPS average')
FIELDS = {
    "draw_cpu_ms": r'draw cpu ([0-9.]+) ms',
    "cp_cpu_ms": r'cp cpu ([0-9.]+)',
    "recorder_cpu_ms": r'recorder cpu ([0-9.]+)',
    "bind_ms": r'; bind ([0-9.]+)',
    "bind_buffers_ms": r'\[buffers ([0-9.]+)',
    "bind_textures_ms": r', textures ([0-9.]+)',
    "bind_dma_ms": r', dma ([0-9.]+)',
    "texture_copy_ms": r', copy ([0-9.]+)',
    "wait_gpu_ms": r'draw waits gpu ([0-9.]+)',
    "wait_submit_ms": r', submit ([0-9.]+)',
    "wait_recorder_ms": r', recorder ([0-9.]+)',
    "wait_frame_ms": r', frame ([0-9.]+)',
    "guest_readback_wait_ms": r'guest readback waits ([0-9.]+)',
}
FIELD_RX = {key: re.compile(value) for key,value in FIELDS.items()}


def analyze(text: str) -> dict:
    windows=[]
    for line in text.splitlines():
        match=SPLIT.search(line)
        if not match:
            continue
        count=int(match.group(1))
        if count <= 0:
            continue
        body=match.group(2)
        values={"frames":count}
        for key, rx in FIELD_RX.items():
            found=rx.search(body)
            if found: values[key]=float(found.group(1))
        windows.append(values)
    seen=[float(x) for x in OLD.findall(text)]
    fps=[float(x) for x,_ in FPS.findall(text)]
    frame_ms=[(float(a),float(b)) for a,b in FRAME.findall(text)]
    if not windows:
        return {"profile":False,"minute_fps":seen,"fps_samples":fps,
                "reason":"SOTC DRAW SPLIT absent: no CPU/GPU bottleneck can be inferred from FPS."}
    total=sum(w["frames"] for w in windows)
    weighted=defaultdict(float)
    for w in windows:
        for key,value in w.items():
            if key!="frames": weighted[key]+=w["frames"]*value
    averages={key:round(value/total,2) for key,value in weighted.items()}
    suspects=[]
    draw=averages.get("draw_cpu_ms")
    cp=averages.get("cp_cpu_ms")
    bind=averages.get("bind_ms")
    rb=averages.get("guest_readback_wait_ms")
    wg=averages.get("wait_gpu_ms")
    wf=averages.get("wait_frame_ms")
    if draw is not None and draw>=20:
        suspects.append("CPU da thread de desenho >=20ms/quadro: investigar binds, draw e dispatch.")
    if cp is not None and cp>=20:
        suspects.append("CPU do processador de comandos >=20ms/quadro: investigar decodificação/JIT.")
    if bind is not None and bind>=8:
        suspects.append("BindResources >=8ms/quadro: preparar descritores fora da thread de desenho.")
    if rb is not None and rb>=10:
        suspects.append("Espera de leitura GPU requisitada pelo jogo >=10ms/quadro: separar fila/envio/GPU/aplicação.")
    if wg is not None and wg>=8:
        suspects.append("CPU aguardando GPU >=8ms/quadro: investigar sincronização e GPU, sem confundir espera com execução.")
    if wf is not None and wf>=8:
        suspects.append("Espera por quadro livre >=8ms/quadro: investigar apresentação/pressão de fila.")
    return {"profile":True,"windows":len(windows),"frames":total,
            "per_frame_ms":averages,"fps_samples":fps,
            "minute_fps":seen,"frame_p50_p99_ms":frame_ms,
            "suspects":suspects or ["Sem causa dominante demonstrada por limiares; verificar quadros lentos e atividade do jogo."]}


def read_log(path: Path) -> str:
    if path.suffix.lower()==".zip":
        with ZipFile(path) as archive:
            names=[name for name in archive.namelist() if name.endswith("android-game.log")]
            if len(names)!=1:
                raise ValueError("Expected exactly one android-game.log inside ZIP")
            return archive.read(names[0]).decode("utf-8","replace")
    return path.read_text(errors="replace")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log",type=Path,help="SotC log ZIP or plain android-game.log")
    args=parser.parse_args()
    result=analyze(read_log(args.log))
    if not result["profile"]:
        print(result["reason"])
        print("Existing minute FPS:",result["minute_fps"])
        raise SystemExit(2)
    print(f"SotC split frames: {result['frames']} across {result['windows']} windows")
    for key,value in sorted(result["per_frame_ms"].items()):
        print(f"  {key}: {value} ms/frame")
    print("Potential targets (needs matched scene/driver confirmation):")
    for item in result["suspects"]:
        print(" - "+item)


if __name__=="__main__":
    main()
