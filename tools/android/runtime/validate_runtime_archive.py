#!/usr/bin/env python3
"""Validate the game-free Android runtime archive before APK packaging."""
import argparse
import hashlib
import io
import json
import posixpath
import stat
import tarfile
import tempfile
from pathlib import Path

try:
    from .validate_runtime_elf import ElfError, inspect
except ImportError:
    from validate_runtime_elf import ElfError, inspect


ROOT = Path(__file__).resolve().parents[3]
MANIFEST_SOURCE = ROOT / 'tools/android/runtime/runtime-manifest.json'
FORBIDDEN = ('com.gp.android', 'eboot.bin', 'eboot.elf', 'sce_module',
             'sce_sys', 'boot-linked.bin', 'save/', 'gow3port/bin',
             'gow3port/lib', 'bbport/rootfs', 'gow3port/rootfs')


class ArchiveError(ValueError):
    pass


def _manifest(path=None):
    return json.loads(Path(path or MANIFEST_SOURCE).read_text())


def _member_map(tar):
    members = {member.name: member for member in tar.getmembers()}
    for name, member in members.items():
        if name.startswith('/') or '..' in Path(name).parts:
            raise ArchiveError('unsafe archive path: %s' % name)
        if member.issym() or member.islnk():
            if member.linkname.startswith('/'):
                raise ArchiveError('absolute symlink target: %s -> %s' %
                                   (name, member.linkname))
            if member.islnk() and member.linkname in members:
                target = member.linkname
            else:
                target = posixpath.normpath(posixpath.join(posixpath.dirname(name),
                                                           member.linkname))
            if target not in members:
                raise ArchiveError('dangling symlink: %s -> %s' % (name, member.linkname))
    return members


def _elf_records(tar, members, manifest):
    explicit = {entry['path'] for entry in manifest['entrypoints']
                if entry.get('launch_via_loader')}
    expected = '/data/user/0/%s/files/%s' % (
        manifest['application_id'], manifest['loader'])
    records = []
    with tempfile.TemporaryDirectory() as directory:
        for name, member in members.items():
            if not member.isfile():
                continue
            stream = tar.extractfile(member)
            if stream is None:
                continue
            data = stream.read()
            if not data.startswith(b'\x7fELF'):
                continue
            path = Path(directory) / ('elf-' + str(len(records)))
            path.write_bytes(data)
            try:
                record = inspect(path)
            except ElfError as error:
                raise ArchiveError('%s: %s' % (name, error)) from error
            interpreter = record['interpreter']
            if interpreter and any(token in interpreter for token in FORBIDDEN):
                raise ArchiveError('%s contains stale interpreter %r' %
                                   (name, interpreter))
            # Shared objects are ELF files too. Most have no PT_INTERP, but a
            # few copied Debian libraries (for example libcap.so.2) do carry
            # the conventional /lib interpreter. They are loaded by the
            # already-running process and are never launched directly, so do
            # not apply the executable-loader rule to runtime libraries.
            is_runtime_library = '/lib/' in name or name.endswith('.so')
            if (interpreter is not None and not is_runtime_library and
                    interpreter != expected and name not in explicit):
                raise ArchiveError(
                    '%s uses %r; expected %r or explicit-loader entrypoint' %
                    (name, interpreter, expected))
            records.append({'path': name, 'interpreter': interpreter,
                            'explicit_loader': name in explicit})
    return records


def validate_archive(archive, digest_file=None, manifest_path=None):
    manifest = _manifest(manifest_path)
    archive = Path(archive)
    if digest_file is not None:
        expected_digest = Path(digest_file).read_text().strip()
        actual_digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if expected_digest != actual_digest:
            raise ArchiveError('payload checksum mismatch: expected %s, got %s' %
                               (expected_digest, actual_digest))
    with tarfile.open(archive, 'r:gz') as tar:
        members = _member_map(tar)
        names = set(members)
        for name in names:
            if any(fragment in name for fragment in FORBIDDEN):
                raise ArchiveError('forbidden game or legacy content: %s' % name)
        if 'runtime-manifest.json' not in members:
            raise ArchiveError('missing runtime-manifest.json')
        embedded = json.loads(tar.extractfile(members['runtime-manifest.json']).read())
        for key in ('schema_version', 'profile', 'application_id', 'java_package', 'abi'):
            if embedded.get(key) != manifest.get(key):
                raise ArchiveError('runtime manifest mismatch for %s' % key)
        roots = {name.split('/', 1)[0] for name in names
                 if name != 'runtime-manifest.json'}
        expected_roots = set(manifest['top_level_roots'])
        if roots != expected_roots:
            raise ArchiveError('runtime top-level layout mismatch: expected %s, got %s' %
                               (sorted(expected_roots), sorted(roots)))
        for directory in manifest['required_directories']:
            member = members.get(directory)
            if member is None or not member.isdir():
                raise ArchiveError('missing required runtime directory: %s' % directory)
        for requirement in manifest['required_paths']:
            name = requirement['path']
            if name not in members:
                raise ArchiveError('missing required path: %s' % name)
            member = members[name]
            kind = requirement['type']
            if kind == 'executable' and not (member.mode & 0o111):
                raise ArchiveError('required executable is not executable: %s' % name)
            if kind == 'loader' and not member.isfile():
                raise ArchiveError('loader is not a regular file: %s' % name)
        for name in manifest['turnip_variants']:
            if name not in members:
                raise ArchiveError('missing Turnip artifact: %s' % name)
        records = _elf_records(tar, members, manifest)
    return {'archive': str(archive), 'members': len(members), 'elf': records,
            'schema_version': manifest['schema_version']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--digest', type=Path)
    parser.add_argument('--manifest', type=Path, default=MANIFEST_SOURCE)
    args = parser.parse_args(argv)
    try:
        result = validate_archive(args.archive, args.digest, args.manifest)
    except (OSError, tarfile.TarError, json.JSONDecodeError, ArchiveError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
