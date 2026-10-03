"""Conservative classification for the externally installed local merge gate.

Only inert documentation/result records are exempt. The controller owns this
policy; a candidate checkout never supplies the policy or its decisions.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

DATA_PREFIXES = ('docs/exec-plans/reviews/',)
DATA_SUFFIXES = ('.md', '.json')


def documentation_only(path: str, modes: tuple[str, ...]) -> bool:
    """An unknown name, executable bit, symlink or submodule requires DB."""
    if not path or any(part in ('', '.', '..') for part in path.split('/')):
        return False
    if any(mode not in ('000000', '100644') for mode in modes):
        return False
    if path == 'README.md':
        return True
    if path.startswith('docs/notes/') and path.endswith('.md'):
        return True
    return path.startswith(DATA_PREFIXES) and path.endswith(DATA_SUFFIXES)


def git(root: Path, *argv: str) -> bytes:
    return subprocess.check_output(['git', *argv], cwd=root, timeout=120)


def classify(root: Path, base: str, head: str) -> dict[str, object]:
    # --no-renames keeps BOTH the deletion and addition in the decision. Renaming
    # an executable into a documentation directory cannot hide the old path.
    raw = git(root, 'diff', '--raw', '-z', '--no-renames', '--no-abbrev', base, head, '--')
    fields = raw.split(b'\0')
    if fields[-1] != b'' or len(fields) % 2 != 1:
        raise ValueError('malformed Git diff')
    changed = []
    required = []
    for offset in range(0, len(fields) - 1, 2):
        metadata = fields[offset].decode('ascii').split()
        if len(metadata) != 5 or not metadata[0].startswith(':'):
            raise ValueError('malformed Git change metadata')
        path = fields[offset + 1].decode('utf-8', errors='surrogateescape')
        changed.append(path)
        if not documentation_only(path, (metadata[0][1:], metadata[1])):
            required.append(path)
    return {'format': 'kineticloop-db-policy-v1', 'base': base, 'head': head,
            'full_database_required': bool(required), 'changed_paths': sorted(changed),
            'requiring_paths': sorted(required)}


def execution_tree(root: Path, head: str) -> str:
    """Bind all executable/configuration/authority inputs, excluding inert records."""
    entries = []
    for raw in git(root, 'ls-tree', '-r', '-z', '--full-tree', head).split(b'\0'):
        if not raw:
            continue
        metadata, encoded_path = raw.split(b'\t', 1)
        mode, kind, oid = metadata.decode('ascii').split()
        path = encoded_path.decode('utf-8', errors='surrogateescape')
        if not documentation_only(path, (mode,)):
            entries.append([path, mode, kind, oid])
    canonical = json.dumps(sorted(entries), ensure_ascii=True, separators=(',', ':')).encode()
    return hashlib.sha256(canonical).hexdigest()
