"""Refresh derived metadata for changed authority paths and new task packets."""
import hashlib
import json
from pathlib import Path

ROOT = Path.cwd()


def refresh(entries):
    for e in entries:
        path = ROOT / e['path']
        e['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        if 'bytes' in e:
            e['bytes'] = path.stat().st_size


path = ROOT / 'CURRENT_DOCUMENT_INDEX.json'
d = json.loads(path.read_text())
refresh(d['documents']); refresh(d['machine_readable'])
path.write_text(json.dumps(d, indent=2) + '\n')
path = ROOT / 'HARNESS_DOCUMENT_MANIFEST.json'
d = json.loads(path.read_text()); refresh(d['files'])
for name in ['KL-075', 'KL-076', 'KL-077']:
    new = f'docs/exec-plans/active/{name}.md'
    p = ROOT / new
    if any(e['path'] == new for e in d['files']):
        continue
    d['files'].append({'path':new,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
path.write_text(json.dumps(d, indent=2) + '\n')
