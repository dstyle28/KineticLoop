"""Refresh only changed derived hashes and append this repair's implementation artifacts."""
import hashlib
import json
from pathlib import Path

root = Path.cwd()
for name, groups in [('CURRENT_DOCUMENT_INDEX.json', ('documents', 'machine_readable')),
                     ('HARNESS_DOCUMENT_MANIFEST.json', ('files',))]:
    path = root / name
    document = json.loads(path.read_text())
    if name == 'HARNESS_DOCUMENT_MANIFEST.json':
        existing = {entry['path'] for entry in document['files']}
        additions = ['tests/harness/test_review_evidence_provenance.py'] + [
            str(p.relative_to(root)) for p in sorted((root / 'docs/exec-plans/evidence/HG-043').iterdir())
            if p.is_file() and not p.name.startswith(('provenance-', 'harness-', 'unit-', 'lint-',
                                                      'typecheck-', 'validation-', 'replay-', 'diff-'))]
        for addition in additions:
            if addition not in existing:
                document['files'].append({'path': addition, 'bytes': 0, 'sha256': ''})
    for group in groups:
        for entry in document[group]:
            content = (root / entry['path']).read_bytes()
            entry['sha256'] = hashlib.sha256(content).hexdigest()
            if 'bytes' in entry:
                entry['bytes'] = len(content)
    path.write_text(json.dumps(document, indent=2) + '\n')
