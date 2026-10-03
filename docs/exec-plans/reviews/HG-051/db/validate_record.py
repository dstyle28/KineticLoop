from pathlib import Path
import importlib.util
import json
import subprocess
import xml.etree.ElementTree as ET
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[5]
REVIEWED = '7141b1dfe48df8f0e25429cf9ff646af6de4b5ce'
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip() == REVIEWED
spec = importlib.util.spec_from_file_location('hg051_db_ce_validate', ROOT / 'tools/harness/compact_evidence.py')
ce = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ce)
record_path = ROOT / 'docs/exec-plans/reviews/HG-051/DB_CONCURRENCY.json'
record = json.loads(record_path.read_bytes())
Draft202012Validator(json.loads((ROOT / 'THREAD_REVIEW.schema.json').read_bytes())).validate(record)
assert record['reviewed_head_sha'] == REVIEWED
assert record['task_identity'] == 'harness-governance-v0.1/HG-051'
assert record['status'] == 'PASS' and record['findings'] == []
total = 0
for ref in record['evidence_refs']:
    assert ce.normalized(ref)
    if ref.startswith('docs/exec-plans/reviews/HG-051/db/'):
        path = ROOT / ref
        assert path.is_file() and not path.is_symlink()
        data = path.read_bytes()
        assert len(data) <= ce.PLAIN_LIMIT
        assert ce.envelope(data) is None
        total += len(data)
    else:
        assert ce.blob(ROOT, ref, REVIEWED)
        ce.read(ROOT, ref, REVIEWED)
assert ce.envelope(record_path.read_bytes()) is None
cases = list(ET.parse(ROOT / 'docs/exec-plans/reviews/HG-051/db/focused.xml').getroot().iter('testcase'))
assert len(cases) == 184
assert all(not any(node.tag in ('failure', 'error', 'skipped') for node in case) for case in cases)
print('PASS: canonical DB_CONCURRENCY schema and exact reviewed identity/revision binding.')
print('PASS: reviewer JUnit 184 cases, zero failures/errors/skips.')
print('PASS: all own references are normalized ordinary regular files within 256KiB per-file bound; all task/governance references are exact reviewed blobs.')
print('Measured own referenced bytes before final validation log output: ' + str(total))
print('Review-created evidence must be committed in the own linear REVIEW_RECORD_ONLY suffix; no ambient files establish committed evidence availability.')
