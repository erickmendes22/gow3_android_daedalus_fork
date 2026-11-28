# Snapdragon UB2 Qualcomm test source

This snapshot uses the UBO renderer from `0eeaec1b3aed1a5ef936523360fe6b378103774f`. It restores the original Qualcomm adapter and the runtime scripts and patch catalog shipped in the UB2 test APK.

Reference APK: `God-of-War-III-Daedalus-UBO-Test-v2.1.8-Qualcomm-arm64.apk`

SHA-256: `5d1edadb0178335ca1b57fc8ad16b4c9f6a64ce35a710af0d469d70f6fdf6781`

- [Reference runtime manifest](ub2-reference-runtime-manifest.json)
- [Component SHA-256 digests](ub2-runtime-component-hashes.json)

The Bionic build uses `tools/android/bionic/build_qualcomm.sh` to build the adapter and pinned libadrenotools source. The UBO staging script packages them with the renderer and the verified 2.1.8 baseline. The reference APK reused prebuilt libadrenotools hooks from TLOU. Rebuilt hooks and the final APK may have different binary hashes. Signing the rebuild requires a separately supplied signing key.
