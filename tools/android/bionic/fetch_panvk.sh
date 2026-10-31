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

# Alternative 2026-10-31 Mesa/PanVK: GPU BC1-BC5 ETC2/EAC and faster BC7
# decode, CSF sync/tiler and robustness fixes. Manual selection ONLY.
# Preserve the original 2a9358a package for reproducible A/B; Adreno untouched.
next_name=Mesa-PanVK-Android-v26.3.1-795ca7ff.adpkg.zip
next_sha=0c61ef0cdd5c9314715c4a0cc34a5929dbd727ce7a30545b947577e83600b900
next_url=https://github.com/zenithblue-oss/panvk-kbase-android/releases/download/panvk-kbase-v26.3.1/$next_name
next_archive="$dest/$next_name"
if [[ -n ${GOW3_PANVK_NEXT_ARCHIVE:-} ]]; then
    cp -f -- "$GOW3_PANVK_NEXT_ARCHIVE" "$next_archive"
elif ! printf '%s  %s\n' "$next_sha" "$next_archive" | sha256sum -c --quiet - 2>/dev/null; then
    next_tmp="$next_archive.part"
    trap 'rm -f "$next_tmp"' EXIT
    curl -fLsS --retry 3 --connect-timeout 20 -o "$next_tmp" "$next_url"
    mv -f "$next_tmp" "$next_archive"
fi
printf '%s  %s\n' "$next_sha" "$next_archive" | sha256sum -c --status - || {
    echo "PanVK v26.3.1 SHA256 mismatch: refusing to bundle" >&2
    rm -f "$next_archive"
    exit 1
}
python3 - "$next_archive" <<'PY'
import json,sys,zipfile
from pathlib import PurePosixPath
with zipfile.ZipFile(sys.argv[1]) as z:
    names=set(z.namelist())
    if 'meta.json' not in names:
        raise SystemExit('PanVK v26.3.1 ZIP missing meta.json')
    meta=json.loads(z.read('meta.json'))
    lib=meta.get('libraryName','')
    if not isinstance(lib,str) or lib.startswith('/') or '..' in PurePosixPath(lib).parts or lib not in names:
        raise SystemExit('PanVK v26.3.1 ZIP missing declared library')
    if int(meta.get('minApi',29))>35:
        raise SystemExit('PanVK v26.3.1 ZIP needs a newer Android')
print('Alternative PanVK 26.3.1: checksum, schema and library verified')
PY
