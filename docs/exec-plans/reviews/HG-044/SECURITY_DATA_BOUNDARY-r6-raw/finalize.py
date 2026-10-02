import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).parent
HEAD = 'cf0b99359d04c136d01fd4c5eeec8a23cd0bbc54'
def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)
def data(path):
    return git('show', HEAD + ':' + path)
audit = json.loads((OUT / 'audit.json').read_text())
assert not audit['errors']
gate = json.loads(data('docs/exec-plans/evidence/HG-044/hg044-final-gate-ec0713f.json'))
assert hashlib.sha256(data('docs/exec-plans/evidence/HG-044/hg044-final-gate-ec0713f.log')).hexdigest() == gate['raw_sha256']
assert gate['exit_code'] == 1
assert b'TypeError' in data('docs/exec-plans/evidence/HG-044/hg044-final-gate-traceback.log')
manifest = json.loads(data('HARNESS_DOCUMENT_MANIFEST.json'))
manifest_checks = []
for row in manifest['files']:
    if row['path'] in ('CURRENT_DOCUMENT_INDEX.json', 'tools/harness/validate_harness.py', 'MILESTONE_CLOSURE.schema.json', '06_KineticLoop_Project_Plan_v0.6_HARNESS_HARDENED.md', 'docs/harness/M3_CLOSURE_CONTRACT.md'):
        contents = data(row['path'])
        assert len(contents) == row['bytes'] and hashlib.sha256(contents).hexdigest() == row['sha256']
        manifest_checks.append(row)
for path in ('tools/harness/validate_harness.py', 'tests/harness/test_m3_milestone_closure.py'):
    assert (ROOT / path).read_bytes() == data(path)
tree = ET.parse(OUT / 'bounded.xml')
cases = list(tree.iter('testcase'))
assert len(cases) == 51 and not any(list(case.iter(tag)) for case in cases for tag in ('failure', 'error', 'skipped'))
assert '51 passed, 39 deselected' in (OUT / 'bounded.stdout').read_text()
broad = (OUT / 'broad-diff.stdout').read_text()
for line in broad.splitlines():
    if line.strip() and not line.startswith('+'):
        assert line.startswith('docs/exec-plans/reviews/HG-044/')
assert not (OUT / 'source-diff.stdout').read_bytes() and not (OUT / 'source-diff.stderr').read_bytes()
summary = {'reviewed_head_sha': HEAD, 'status': 'PASS', 'bounded_test_count': len(cases), 'selected_capture_count': len(audit['selected_captures']), 'changed_path_count': audit['changed_path_count'], 'recursive_integrations': len(audit['recursive_integrations']), 'recursive_binding_count': len(audit['chain_inventory']), 'manifest_checks': manifest_checks, 'source_diff_exit_code': 0, 'broad_diff_exit_code': 2, 'broad_diff_reason': 'Preserved own-review unified-diff context whitespace only', 'original_gate_failure_raw_hash_verified': True, 'audit_errors': audit['errors']}
(OUT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
refs = ['docs/exec-plans/reviews/HG-044/SECURITY_DATA_BOUNDARY-r6-raw/' + name for name in ('assessment.md', 'audit.py', 'audit.json', 'audit.stdout', 'audit.stderr', 'bounded.stdout', 'bounded.stderr', 'bounded.xml', 'result-mode-probe.py', 'result-mode-probe.json', 'integer-probe.py', 'integer-probe.json', 'source-diff.patch', 'source-diff.stdout', 'source-diff.stderr', 'broad-diff.stdout', 'broad-diff.stderr', 'summary.json', 'finalize.py')]
review = {'task_identity': 'harness-governance-v0.1/HG-044', 'reviewed_head_sha': HEAD, 'review_type': 'SECURITY_DATA_BOUNDARY', 'status': 'PASS', 'findings': [], 'evidence_refs': refs, 'review_contract_version': 'v0.2'}
Draft202012Validator(json.loads((ROOT / 'THREAD_REVIEW.schema.json').read_text())).validate(review)
for ref in refs:
    assert (ROOT / ref).is_file() and not (ROOT / ref).is_symlink()
(OUT.parent / 'SECURITY_DATA_BOUNDARY.json').write_text(json.dumps(review, indent=2) + '\n')
print(json.dumps(summary), flush=True)
hashes = [{'path': str(path.relative_to(ROOT)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'bytes': path.stat().st_size} for path in sorted(OUT.iterdir()) if path.is_file() and path.name != 'raw-inventory.json']
(OUT / 'raw-inventory.json').write_text(json.dumps(hashes, indent=2) + '\n')
