"""Refresh only authorized derived hashes/own delivery manifest additions."""
import hashlib
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]

def hashed(path):
    data = (ROOT / path).read_bytes()
    return {'path': path, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}

def main():
    index_path = ROOT / 'CURRENT_DOCUMENT_INDEX.json'
    index = json.loads(index_path.read_text())
    for group in ('documents', 'machine_readable'):
        for entry in index[group]:
            entry['sha256'] = hashed(entry['path'])['sha256']
    index_path.write_text(json.dumps(index, indent=2) + '\n')
    manifest_path = ROOT / 'HARNESS_DOCUMENT_MANIFEST.json'
    manifest = json.loads(manifest_path.read_text())
    for entry in manifest['files']:
        if (ROOT / entry['path']).is_file():
            entry.update(hashed(entry['path']))
    existing = {e['path'] for e in manifest['files']}
    for path in sorted((ROOT / 'docs/exec-plans/evidence/HG-056').rglob('*')):
        relative = str(path.relative_to(ROOT))
        # Executed output is source-bound and need not be indexed individually.
        if path.is_file() and relative not in existing and '/checks-' not in relative:
            manifest['files'].append(hashed(relative))
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')

if __name__ == '__main__':
    main()
