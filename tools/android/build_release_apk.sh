#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/../.."
exec bash tools/android/apk/build_release_apk.sh "$@"
