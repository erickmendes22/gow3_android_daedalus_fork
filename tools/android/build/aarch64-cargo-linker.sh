#!/usr/bin/env bash
# Rust extractor is built for the SAME Debian ARM64 sysroot as gow3-probe.
set -euo pipefail
: "${GOW3_ARM64_SYSROOT:?Set GOW3_ARM64_SYSROOT to the aarch64 Debian sysroot}"
exec clang --target=aarch64-linux-gnu --sysroot="$GOW3_ARM64_SYSROOT" -fuse-ld=lld "$@"
