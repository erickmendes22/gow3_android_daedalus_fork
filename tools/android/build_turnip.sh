#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/../.."
exec bash tools/android/build/build_turnip.sh "$@"
