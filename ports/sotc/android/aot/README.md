# Shadow of the Colossus: ARM64 AOT bootstrap (experimental)

**Not an AOT gameplay APK.** This initial change does not remove FEX from the
installed SotC 0.1.53 application and does not claim an FPS improvement.

## Confirmed from Android log

In the 2026-11-21 19:40 SotC diagnostic, FEXCore JIT is active, with its TSO
configuration unchanged. The second and third complete minutes report 28.6
and 28.8 FPS. The third minute has 55 frames over 50 ms. PhysX clothing
reported 20.58 ms simulation but is not proven to be the sole bottleneck.

The TLOU experimental ARM64 native code is the technical reference. Its
v3 vs v4 TSO comparison measured 56.8 vs 56.8 flips/s in unsynchronized
runs, so changing TSO did not demonstrate an FPS gain. Its TSO-OFF profile
is expressly unsafe/experimental; never deploy that as SotC default.

## Implemented now

- Local compiler frontend validates the actual eboot digest against the
  prepared SotC image analysis and checks EU/US title IDs.
- Validates BBPROBE5 tables and duplicates all SotC BBPATCH2 edits on an
  isolated private image BEFORE AOT codegen, avoiding stale patched code.
- Refuses patch overlap, out-of-bounds changes, corrupted tables and
  unintended modifications to original files.
- Calls TSO-correct ARM64 bb-recomp (TLOU-patched v3/v4/v5), with
  --tso, --resume-entries, --no-callee-saved, and explicit ARMv8.2.
- Verifies compiled AArch64 ELF, compiler ABI, checksum, unit coverage,
  and absence of unsupported LoadMemTSO/StoreMemTSO IR operations.
- AOT code remains in a separate work directory. FEX is unchanged.
- Lightweight host CI checks code and safety invariants without building
  yet another unchanged APK.

Example with an independently obtained TSO-compatible Android compiler,
user's own game and private app storage:

    python3 sotc_aot_compile.py \
        --game /private/ShadowOfTheColossus \
        --prepared /private/sotcport/sotc-out \
        --out /private/sotc-aot-work \
        --compiler /private/tools/libbbrecomp.so \
        --bundle-dir /private/tools/bundle \
        --jobs 3 --shards 64 --dry-run

Remove --dry-run only after provisioning the patched AOT compiler. Sony game
data MUST remain local and must never be uploaded to build CI.

## Required before game can run without FEX

1. Adapt Bloodborne/TLOU AOT guest CPU dispatcher for SotC's distinct
   GuestContext (guest_context_get/guest_context_set) continuation ABI,
   PS4 fibers, callbacks, GS/FS per thread and host signal handling.
2. Verify indirect entry coverage, pretranslated libc.prx/libSceFios2.prx
   and any native patch sites; reject uncovered or dirty units.
3. Preserve runtime code patch semantics, traps, TLS, exception recovery,
   write protection and GPU readback behavior. No unsafe TSO removal.
4. Run an opt-in AOT Android build and compare identical forest paths on
   device with FEX baseline, including saves, visuals, physics and stalls.

At 28.8 FPS, mean frame cost is about 34.72 ms. Reaching 30 FPS needs
33.33 ms/frame, or ~1.39 ms (4.0%) of critical-path savings. AOT may
reduce JIT/dispatch overhead but CANNOT remove GPU or PhysX costs; expected
FPS gains are unknown until SotC native gameplay is actually profiled.
