#!/usr/bin/env python3
"""Repackage exact verified SotC 0.1.32 native ELF and driver files with sequential readback config only."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile
import zipfile


def repack(base_apk: Path, root: Path) -> None:
    runner = (root / "ports/sotc/android/run-sotc-bionic.sh").read_bytes()
    if b"export SOTC_LOD_LINGER=" not in runner or b"SOTC_LOD_LEVEL=" not in runner:
        raise RuntimeError("Real High texture LOD streaming not configured")
    if b"SOTC_TAA_OFF=" not in runner:
        raise RuntimeError("TAA-history workaround absent")
    release = root / "out/android-release/assets"
    release.mkdir(parents=True, exist_ok=True)
    out = release / "runtime.payload"
    required = {"sotcport/run-sotc-bionic.sh", "sotcport/sotc.default.ini",
                "sotcport/sotc.ini", "runtime-manifest.json"}
    copied = set()
    signatures = {}
    with zipfile.ZipFile(base_apk) as apk:
        jni = root / "out/bionic/apk-jni"
        # Two JNI bridges already come from tools/android/bridges and
        # androidx.graphics.path comes from the Android dependency. Readding
        # them from the source APK creates duplicate JNI resources in Gradle.
        # Only libgow3present.so is produced outside those source sets.
        name = "lib/arm64-v8a/libgow3present.so"
        target = jni / "arm64-v8a/libgow3present.so"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(apk.read(name))
        for essential in ("libfxdisplay.so", "libfxio.so"):
            if not (root / "tools/android/bridges/arm64-v8a" / essential).is_file():
                raise RuntimeError("Missing bundled bridge: " + essential)
        if not target.is_file():
            raise RuntimeError("Missing verified JNI: libgow3present.so")
        payload = io.BytesIO(apk.read("assets/runtime.payload"))
        with tarfile.open(fileobj=payload, mode="r:gz") as source:
            with tarfile.open(out, mode="w:gz", compresslevel=6) as dest:
                for member in source:
                    if not member.isfile():
                        dest.addfile(member)
                        continue
                    binary = source.extractfile(member)
                    assert binary is not None
                    if member.name in required:
                        data = binary.read()
                        if member.name == "sotcport/run-sotc-bionic.sh":
                            data = runner
                        elif member.name.endswith(".ini"):
                            if data.count(b"sotc_readbacks=2") != 1 or b"sotc_rb_stream=" in data:
                                raise RuntimeError("Wrong source 0.1.32 defaults")
                            data = data.replace(b"sotc_readbacks=2",
                                                b"sotc_readbacks=2\nsotc_rb_stream=1")
                        else:
                            record = json.loads(data)
                            if record.get("version") != "0.1.32-boot-test":
                                raise RuntimeError("Wrong native source runtime")
                            record["version"] = "0.1.34-boot-test"
                            record["runtime_name"] = "sotc-daedalus-bionic-0.1.34"
                            data = (json.dumps(record, indent=2) + "\n").encode()
                        member.size = len(data)
                        dest.addfile(member, io.BytesIO(data))
                        copied.add(member.name)
                    else:
                        if member.name in ("sotcport/arm64/lib/libbbgpu.so",
                                           "sotcport/arm64/bin/sotc-probe",
                                           "sotcport/arm64/drivers/gen8/libvulkan_freedreno.so"):
                            data = binary.read()
                            signatures[member.name] = hashlib.sha256(data).hexdigest()
                            dest.addfile(member, io.BytesIO(data))
                        else:
                            dest.addfile(member, binary)
    essential = {"sotcport/arm64/lib/libbbgpu.so", "sotcport/arm64/bin/sotc-probe"}
    if copied != required or not essential.issubset(signatures):
        raise RuntimeError("Missing required payload entries or native ELF checksums")
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    (release / "runtime.sha256").write_text(digest + "\n")
    with tarfile.open(out, "r:gz") as t:
        s = t.extractfile("sotcport/run-sotc-bionic.sh").read()
        assert b"export SOTC_LOD_LINGER=" in s
        assert b"export SOTC_UPLOAD_BUDGET_MB=0" in s
        assert b"SOTC_VM_RANGE_CACHE=" in s
        assert b"SOTC_RB_STREAM_MAX_KB=" in s
        assert b"sotc_blur_suppression=1" in t.extractfile("sotcport/sotc.ini").read()
        assert b"sotc_fast_bind=0" in t.extractfile("sotcport/sotc.ini").read()
        assert b"sotc_rb_stream=1" in t.extractfile("sotcport/sotc.ini").read()
        assert b"SOTC_RB_STREAM=" in s
        assert b"SOTC_RB_STREAM_MAX_KB=" in s
        assert b"sotc_record_thread=0" in t.extractfile("sotcport/sotc.ini").read()
        assert json.load(t.extractfile("runtime-manifest.json"))["version"] == "0.1.34-boot-test"
        for key, old_digest in signatures.items():
            assert hashlib.sha256(t.extractfile(key).read()).hexdigest() == old_digest
    print("PASS: 0.1.34 verified-native repack, native ELF files bit-identical; sha256", digest)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--base-apk", type=Path, required=True)
    p.add_argument("--root", type=Path, default=Path("."))
    args = p.parse_args()
    repack(args.base_apk, args.root)
