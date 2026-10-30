#!/usr/bin/env bash
# Official ducvd89/Bloodborne-Android PanVK v3.2 CSF Android/Bionic build.
# Experimental only: neither Bloodborne nor GoW3 gameplay is validated on Mali.
set -euo pipefail
cd -- "$(dirname -- "$0")/../../.."
name=PanVK-android-v3.2-universal-2a9358a.zip
sha=68d4eccc1442cb0bef08228c90127388e68bf6087898abc492c717b9a06ca61f
url=https://github.com/ducvd89/Bloodborne-Android/releases/download/panvk-android-v3.2-2a9358a/PanVK-android-v3.2-universal-2a9358a.zip
dest="out/android-release/assets/drivers"
mkdir -p "$dest"
archive="$dest/$name"
if [[ -n ${GOW3_PANVK_ARCHIVE:-} ]]; then
    cp -f -- "$GOW3_PANVK_ARCHIVE" "$archive"
elif ! printf '%s  %s\n' "$sha" "$archive" | sha256sum -c --quiet - 2>/dev/null; then
    tmp="$archive.part"
    trap 'rm -f "$tmp"' EXIT
    curl -fLsS --retry 3 --connect-timeout 20 -o "$tmp" "$url"
    mv -f "$tmp" "$archive"
fi
printf '%s  %s\n' "$sha" "$archive" | sha256sum -c --status - || {
    echo "PanVK archive SHA256 mismatch: refusing to package an unverified driver" >&2
    rm -f "$archive"
    exit 1
}
python3 - "$archive" <<'PY'
import json,sys,zipfile
from pathlib import PurePosixPath
with zipfile.ZipFile(sys.argv[1]) as z:
    names=set(z.namelist())
    if 'meta.json' not in names:
        raise SystemExit('PanVK ZIP missing meta.json')
    meta=json.loads(z.read('meta.json'))
    lib=meta.get('libraryName','')
    if not isinstance(lib,str) or lib.startswith('/') or '..' in PurePosixPath(lib).parts or lib not in names:
        raise SystemExit('PanVK ZIP missing its declared Vulkan library')
    if int(meta.get('minApi',35))>35:
        raise SystemExit('PanVK ZIP requires a newer Android than 15')
print('Bundled PanVK v3.2: checksum and metadata verified (Mali testing only)')
PY
