#!/usr/bin/env python3
"""Preflight and install the Gest Git package without clobbering other hooks."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

PROVENANCE = Path('.agents/gest-git-install.json')
CONFIGS = (Path('.claude/settings.json'), Path('.codex/hooks.json'))


def fail(message):
    raise ValueError(message)


def git(source, *args):
    return subprocess.check_output(['git', '-C', str(source), *args], text=True, stderr=subprocess.PIPE).strip()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        fail(f'Invalid JSON in {path}: {exc}')
    if not isinstance(value, dict):
        fail(f'Expected a JSON object in {path}')
    return value


def merge_config(existing, incoming, path):
    result = json.loads(json.dumps(existing))
    if not isinstance(incoming.get('hooks'), dict) or not isinstance(result.get('hooks', {}), dict):
        fail(f'Invalid hooks object in {path}')
    hooks = result.setdefault('hooks', {})
    for event, groups in incoming['hooks'].items():
        current = hooks.setdefault(event, [])
        if not isinstance(current, list) or not isinstance(groups, list):
            fail(f'Invalid hook groups for {event} in {path}')
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get('hooks'), list):
                fail(f'Invalid hook group for {event} in {path}')
            selector = {key: value for key, value in group.items() if key != 'hooks'}
            match = None
            for candidate in current:
                if not isinstance(candidate, dict) or not isinstance(candidate.get('hooks'), list):
                    fail(f'Invalid existing hook group for {event} in {path}')
                if {key: value for key, value in candidate.items() if key != 'hooks'} == selector:
                    match = candidate
                    break
            if match is None:
                match = dict(selector, hooks=[])
                current.append(match)
            for hook in group['hooks']:
                if not isinstance(hook, dict) or not isinstance(hook.get('command'), str):
                    fail(f'Invalid hook command for {event} in {path}')
                same_command = [item for item in match['hooks'] if isinstance(item, dict) and item.get('command') == hook['command']]
                if any(item != hook for item in same_command):
                    fail(f'Conflicting hook command {hook["command"]!r} in {path}; resolve it manually')
                if not same_command:
                    match['hooks'].append(hook)
    return result


def source_revision(source, requested):
    try:
        top = Path(git(source, 'rev-parse', '--show-toplevel')).resolve()
        if top != source.resolve():
            fail(f'Source must be a Git repository root: {source}')
        revision = git(source, 'rev-parse', '--verify', f'{requested or "HEAD"}^{{commit}}')
        remote = git(source, 'config', '--get', 'remote.origin.url') if git_has_remote(source) else None
        dirty = bool(git(source, 'status', '--porcelain', '--untracked-files=all'))
        return revision, remote, dirty
    except subprocess.CalledProcessError as exc:
        fail(f'Cannot resolve source Git revision: {exc.stderr.strip()}')


def git_has_remote(source):
    return subprocess.run(['git', '-C', str(source), 'config', '--get', 'remote.origin.url'], capture_output=True).returncode == 0


def source_files(source, pinned):
    if not pinned:
        return source, None
    temp = tempfile.TemporaryDirectory(prefix='gest-git-source-')
    archive = Path(temp.name) / 'source.tar'
    with archive.open('wb') as handle:
        run = subprocess.run(['git', '-C', str(source), 'archive', '--format=tar', pinned], stdout=handle, stderr=subprocess.PIPE)
    if run.returncode:
        temp.cleanup()
        fail(f'Cannot archive pinned source {pinned}: {run.stderr.decode(errors="replace").strip()}')
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            dest = (Path(temp.name) / member.name).resolve()
            if not dest.is_relative_to(Path(temp.name).resolve()):
                temp.cleanup()
                fail('Pinned source archive contains an unsafe path')
            if member.isfile():
                dest.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(member) as inp, dest.open('wb') as out:
                    shutil.copyfileobj(inp, out)
                dest.chmod(member.mode)
            elif member.isdir():
                dest.mkdir(parents=True, exist_ok=True)
            elif not (member.issym() or member.islnk()):
                temp.cleanup()
                fail('Pinned source archive contains an unsupported entry')
    return Path(temp.name), temp


def reject_symlinks(root, relative):
    """Reject links in every managed path, including dangling links."""
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            fail(f'Symlinked managed path is not allowed: {current}')


def gather_files(source, mode, hooks):
    files = {}
    pattern = 'g*' if mode == 'sync' else '*'
    reject_symlinks(source, Path('.agents/skills'))
    for folder in sorted((source / '.agents/skills').glob(pattern)):
        reject_symlinks(source, folder.relative_to(source))
        if folder.is_dir():
            for path in folder.rglob('*'):
                reject_symlinks(source, path.relative_to(source))
                if path.is_file():
                    files[path.relative_to(source)] = path.read_bytes()
    if hooks:
        for base in ('.claude/hooks', '.codex/hooks'):
            reject_symlinks(source, Path(base))
            for path in sorted((source / base).glob('*')):
                reject_symlinks(source, path.relative_to(source))
                if path.is_file():
                    files[path.relative_to(source)] = path.read_bytes()
    if mode == 'install':
        reject_symlinks(source, Path('AGENTS.template.md'))
        files[Path('AGENTS.md')] = (source / 'AGENTS.template.md').read_bytes()
    return files


def atomic_write(path, data, mode=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f'.{path.name}.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(name, mode)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', type=Path)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--source-commit')
    parser.add_argument('--mode', choices=('install', 'sync'), default='install')
    parser.add_argument('--hooks', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if args.target.is_symlink() or args.source.is_symlink():
        fail('Source and target repository roots must not be symlinks')
    target = args.target.resolve()
    source = args.source.resolve()
    if not target.is_dir():
        fail(f'Target does not exist: {target}')
    revision, remote, dirty = source_revision(source, args.source_commit)
    if args.source_commit and dirty:
        print('Installing clean pinned commit; working-tree changes are excluded.', file=sys.stderr)
    selected, temp = source_files(source, revision if args.source_commit else None)
    try:
        files = gather_files(selected, args.mode, args.mode == 'install' or args.hooks)
        reject_symlinks(target, PROVENANCE)
        old = read_json(target / PROVENANCE)
        old_hashes = old.get('managed_files', {})
        if not isinstance(old_hashes, dict):
            fail(f'Invalid managed_files in {target / PROVENANCE}')
        planned = {}
        for relative, data in files.items():
            destination = target / relative
            reject_symlinks(target, relative)
            if relative == Path('AGENTS.md') and destination.exists():
                continue
            if destination.exists() and destination.is_dir():
                fail(f'Destination is a directory: {destination}')
            if destination.exists() and relative != Path('AGENTS.md'):
                previous = old_hashes.get(relative.as_posix())
                current = digest(destination.read_bytes())
                if current != digest(data) and current != previous:
                    fail(f'Existing managed file differs from source and previous install: {destination}')
            planned[relative] = data
        configs = {}
        if args.mode == 'install' or args.hooks:
            for relative in CONFIGS:
                reject_symlinks(selected, relative)
                reject_symlinks(target, relative)
                incoming = read_json(selected / relative)
                existing = read_json(target / relative)
                merged = merge_config(existing, incoming, target / relative)
                configs[relative] = (json.dumps(merged, indent=2, ensure_ascii=False) + '\n').encode()
        metadata = {
            'schema_version': 1,
            'source_repository': remote,
            'source_revision': revision,
            'source_worktree_dirty': dirty if not args.source_commit else False,
            'source_checkout_dirty': dirty,
            'source_requested_commit': args.source_commit,
            'managed_files': dict(old_hashes),
        }
        for relative, data in planned.items():
            if relative != Path('AGENTS.md'):
                metadata['managed_files'][relative.as_posix()] = digest(data)
        if args.dry_run:
            print(f'Would install {len(planned)} files and merge {len(configs)} hook settings in {target} from {revision}')
            return
        for relative, data in planned.items():
            source_path = selected / ('AGENTS.template.md' if relative == Path('AGENTS.md') else relative)
            atomic_write(target / relative, data, source_path.stat().st_mode & 0o777)
        for relative, data in configs.items():
            if not (target / relative).exists() or (target / relative).read_bytes() != data:
                atomic_write(target / relative, data)
        atomic_write(target / PROVENANCE, (json.dumps(metadata, indent=2) + '\n').encode())
        print(f'Installed Gest Git package in {target} from {revision} (dirty source: {metadata["source_worktree_dirty"]})')
        if (target / 'AGENTS.md').exists() and Path('AGENTS.md') not in planned and args.mode == 'install':
            print('Kept existing AGENTS.md.', file=sys.stderr)
    finally:
        if temp:
            temp.cleanup()


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as exc:
        print(f'Install failed: {exc}', file=sys.stderr)
        sys.exit(1)
