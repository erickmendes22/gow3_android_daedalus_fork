#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/../.."
exec bash tools/android/device/deploy-gow3.sh "$@"
