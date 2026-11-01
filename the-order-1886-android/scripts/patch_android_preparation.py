#!/usr/bin/env python3
"""Permit trusted Android OS path aliases without allowing user-controlled symlinks."""
from pathlib import Path
import sys

OLD = '''def safe_path(path):
    """Check before resolving, so a selected junction cannot hide its redirection."""
    path = Path(path).absolute()
    for ancestor in (*reversed(path.parents), path):
        try:
            _stat(ancestor)
        except FileNotFoundError:
            pass
    return path.resolve()
'''

NEW = '''def safe_path(path):
    """Reject user symlinks but permit Android's trusted mount-path aliases.

    The Android launcher explicitly supplies its app-private state directory
    and its selected game directory. Only their OS-managed ancestor aliases
    can be skipped; every component beneath these roots is still lstat-checked.
    Without explicit roots the desktop policy is left unchanged.
    """
    path = Path(path).absolute()
    roots = tuple(os.environ.get(key, '') for key in (
        'ORDER1886_ANDROID_TRUSTED_GAME_ROOT',
        'ORDER1886_ANDROID_TRUSTED_STATE_ROOT'))
    for raw_root in roots:
        if not raw_root or not os.path.isabs(raw_root):
            continue
        root = Path(raw_root).absolute()
        if path != root and root not in path.parents:
            continue
        candidate = root
        for part in path.relative_to(root).parts:
            candidate = candidate / part
            try:
                _stat(candidate)
            except FileNotFoundError:
                pass
        resolved_root = root.resolve()
        resolved = path.resolve()
        if resolved != resolved_root and resolved_root not in resolved.parents:
            raise ValueError(f'Path escapes trusted Android root: {path}')
        return resolved
    for ancestor in (*reversed(path.parents), path):
        try:
            _stat(ancestor)
        except FileNotFoundError:
            pass
    return path.resolve()
'''

def patch(path):
    source = Path(path)
    text = source.read_text(encoding='utf-8')
    if OLD not in text:
        raise RuntimeError('Pinned upstream safe_path changed; inspect before applying Android patch')
    source.write_text(text.replace(OLD, NEW, 1), encoding='utf-8')
    print(f'Android trusted-root path fix: {source}')

if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('usage: patch_android_preparation.py scripts/order1886_mods.py')
    patch(sys.argv[1])
