#!/usr/bin/env python3
"""Static binary-only Bachata S4 0.2.5 vs GoW3 Mali audit. Never redistributes APKs."""
from __future__ import annotations
import hashlib, io, os, pathlib, re, subprocess, sys, zipfile

BACHATA_EXPECTED_SHA256="1df49463f396df8b6f042230bdc1bb9f948b8e69894c378915920875c40ab0ee"
root=pathlib.Path("bachata_binary_audit")
root.mkdir(exist_ok=True)
report=[]
def say(s=""):
    report.append(s)
    print(s, flush=True)
def run(*cmd):
    try:
        p=subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=110, check=False)
        return p.stdout.decode("utf-8", "replace")[:120000]
    except (OSError, subprocess.TimeoutExpired) as exc:
        return str(exc)
def sha(buf):
    return hashlib.sha256(buf).hexdigest()
def inspect_zip(zfile, source, depth=0):
    if depth>2: return []
    files=[]
    try:
        with zipfile.ZipFile(zfile) as z:
            infos=[e for e in z.infolist() if not e.is_dir()]
            say(f"Archive {source}: {len(infos)} entries")
            for e in sorted(infos, key=lambda i:i.file_size,reverse=True)[:15]:
                say(f"  large {e.file_size//1024//1024:>3} MiB {e.filename[:110]}")
            for e in infos:
                name=e.filename.lower()
                basename=pathlib.PurePosixPath(name).name
                if name.endswith((".apk",".zip")) and depth<2 and e.file_size<550000000:
                    try: files.extend(inspect_zip(io.BytesIO(z.read(e)),source+"/"+e.filename,depth+1))
                    except Exception as ex: say(f"Unable to read nested archive {e.filename}: {ex}")
                    continue
                # Also consider unpacked Linux-ELF executable cores without a .so suffix.
                likely=e.file_size>100000 and (
                    name.endswith((".so",".elf",".bin")) or
                    "shadps4" in basename or "panvk" in name or "fex" in basename
                )
                if not likely: continue
                try:
                    blob=z.read(e)
                except Exception: continue
                if blob[:4]!=b"\x7fELF": continue
                files.append((source,e.filename,blob))
    except Exception as ex:
        say(f"Could not parse archive {source}: {ex}")
    return files

def interesting(p):
    k=p.lower()
    return any(x in k for x in ("bachata_native","panfrost","panvk","gow3gpu","shadps4","fexcore","libfex", "libvulkan"))
KEYS=[
 ("barrier", r"barrier|hazard|synchroni[sz]|flushall|vkcmdpipelinebarrier|waitformem|waitforfence"),
 ("submit_wait", r"gpu.?tick|timeline|waitsemaphores|vkqueuesubmit|vkgetsemaphorecounter|frames.?ahead|in.?flight"),
 ("recording", r"recorder|record.thread|worker.?thread|draw.?pipe|prepared.?draw|draw.?worker|fex.?multiblock"),
 ("texture", r"bcn|etc2|transcod|image.?pool|bc.?alias|rgba128|texture.?memo|cached.?image|tiler.?heap"),
 ("memory", r"gc.?pressure|memory.?budget|trim.?buffer|vma.?budget|rebind|heap.?renew|panvk_kbase"),
 ("display", r"ahardwarebuffer|native.?ahb|cpu.?present|videoout|direct.?present|surfaceflinger"),
]
def inspect_blob(group, path, blob):
    out=root/(group+"-"+re.sub(r"[^A-Za-z0-9._-]","_",path[-90:]))
    out.write_bytes(blob)
    stats={"group":group,"path":path,"size":len(blob),"sha":sha(blob)}
    dynamic=run("readelf","-Wd",str(out))
    needed=re.findall(r"\(NEEDED\).*?\[(.*?)\]",dynamic)
    notes=run("readelf","-n",str(out))
    buildid=re.findall(r"Build ID: ([0-9a-fA-F]+)",notes)
    sym=run("readelf","-Ws",str(out))
    symnames=[]
    for line in sym.splitlines():
        if re.search(r"(\bLOCAL\b|\bGLOBAL\b|\bWEAK\b)",line):
            symbol=line.split()[-1] if line.split() else ""
            if re.search(r"(?i)(garbagecollectimages|downloadimagememory|bindtextures|drawrecord|scheduler|submitexecution|rasterizer|panvk.*heap)",symbol):
                if len(symnames)<35: symnames.append(symbol[:140])
    # Stream the COMPLETE ELF strings, not the first 120 KB (which are dominated by symbols).
    # Only collect distinctive/diagnostic strings, capped by category to keep the report short.
    matches={key:[] for key,_ in KEYS}
    patterns=[(key,re.compile(pattern,re.I)) for key,pattern in KEYS]
    proc=subprocess.Popen(["strings","-a","-n","9",str(out)],stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL,text=True,errors="replace")
    try:
        for rawline in proc.stdout:
            line=rawline.strip()
            if len(line)>400: continue
            for key,pattern in patterns:
                if pattern.search(line) and line not in matches[key] and len(matches[key])<45:
                    matches[key].append(line)
    finally:
        proc.stdout.close()
        proc.wait(timeout=90)
    # Target actual implementation symbols and sizes; avoid inferring from generic Vulkan strings.
    nm=run("nm","-C","-S","--defined-only",str(out),limit=16000000)
    targets=[
        "Vulkan::CommandRecorder::Reserve", "Vulkan::CommandRecorder::Publish",
        "Vulkan::CommandRecorder::Sync", "Vulkan::CommandRecorder::WorkerLoop",
        "VideoCore::TileManager::EncodeEtc2",
        "VideoCore::TileManager::GetEtc2EncodePipeline",
        "Vulkan::Instance::RefreshAllocatorMemoryBudget",
        "Vulkan::Instance::GetLiveGpuMemoryBudget",
        "VideoCore::BufferCache::BindVertexBuffers",
        "Vulkan::Scheduler::SubmitExecution", "Vulkan::Scheduler::RecorderThread",
        "Vulkan::BcnTranscodeState::Record", "Vulkan::BcnTranscodeState::RecordBatch",
    ]
    exact={key:[ln.strip()[:300] for ln in nm.splitlines() if key in ln][:3] for key in targets}
    stats.update(needed=needed,buildid=buildid[:2],symbols=symnames,markers=matches,exact=exact)
    out.unlink(missing_ok=True)
    return stats
if len(sys.argv) not in (3,4): raise SystemExit("usage: compare_bachata_025_elf.py bachata.apk gow3-native.zip [gow3-apk-artifact.zip]")
bachata=pathlib.Path(sys.argv[1]);gow=pathlib.Path(sys.argv[2])
if sha(bachata.read_bytes())!=BACHATA_EXPECTED_SHA256:
    raise SystemExit("OFFICIAL BACHATA APK SHA-256 mismatch: abort")
say("# Actual ELF binary audit: Bachata S4 0.2.5 vs GoW3 Mali")
say(f"Verified official Bachata APK sha256 {BACHATA_EXPECTED_SHA256}")
allstats={}
inputs=[("bachata025",bachata),("gow3-native",gow)]
if len(sys.argv)==4: inputs.append(("gow3-apk",pathlib.Path(sys.argv[3])))
for origin,p in inputs:
    files=inspect_zip(p,origin)
    say(f"ELF entries {origin}: {len(files)}")
    for src,name,blob in sorted(files,key=lambda v:len(v[2]),reverse=True)[:25]:
        say(f"  ELF {len(blob)//1048576:>3} MiB {name[:120]}")
    selected=[item for item in files if interesting(item[1])]
    if not selected: selected=sorted(files,key=lambda v:len(v[2]),reverse=True)[:4]
    selected=sorted(selected,key=lambda v:len(v[2]),reverse=True)[:15]
    allstats[origin]=[]
    for source,name,blob in selected:
        stats=inspect_blob(origin,name,blob)
        allstats[origin].append(stats)
        say(f"## {origin} | {name}")
        say(f"Bytes: {stats['size']} SHA-256: {stats['sha']}")
        say("NEEDED: "+", ".join(stats["needed"]))
        say("BuildID: "+", ".join(stats["buildid"]))
        for key,vals in stats["markers"].items():
            if vals: say(f"{key}: "+" | ".join(vals)[:1400])
        if stats["symbols"]: say("symbols: "+" | ".join(stats["symbols"])[:1400])
        for symbol, rows in stats["exact"].items():
            if rows: say("FUNCTION: "+symbol+" | "+" | ".join(rows))
say("## Comparison cautions")
say("String markers and exported symbols are presence evidence, not proof of performance, codepath selection, or the absence of stripped implementations.")
say("No native .so file and no executable binary is redistributed by this audit.")
(root/"BACHATA_025_GOW3_BINARY_AUDIT.md").write_text("\n".join(report)+"\n",encoding="utf-8")
