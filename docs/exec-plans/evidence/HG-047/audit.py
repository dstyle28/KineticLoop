"""Audit the compact concern against the integrated protected base without rewriting history."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[4]
base, tested = sys.argv[1:]

def git(*args):
    return subprocess.check_output(['git', *args], cwd=root)

assert git('rev-parse', 'HEAD').decode().strip() == tested
subprocess.run(['git', 'merge-base', '--is-ancestor', base, tested], cwd=root, check=True)
expected = {
    'CURRENT_DOCUMENT_INDEX.json', 'HARNESS_DOCUMENT_MANIFEST.json',
    'docs/exec-plans/governance/HG-047.yaml',
    'docs/harness/EVIDENCE_STORAGE_POLICY.md', 'docs/harness/HARNESS_GOVERNANCE_CONTRACT.md',
    'docs/harness/LOCAL_DB_CI.md', 'docs/harness/M3_CLOSURE_CONTRACT.md',
    'docs/harness/MERGE_GATE.md', 'docs/harness/THREAD_RESULT_CONTRACT.md',
    'docs/harness/THREAD_REVIEW_CONTRACT.md', 'tests/harness/test_compact_evidence.py',
    'tests/harness/test_local_gate.py', 'tests/harness/test_m3_milestone_closure.py',
    'tests/harness/test_review_evidence_provenance.py', 'tests/harness/test_validator.py',
    'tools/harness/README.md', 'tools/harness/compact_evidence.py',
    'tools/harness/local_gate.py', 'tools/harness/validate_harness.py',
}
changed = set(git('diff', '--name-only', '--no-renames', base, tested).decode().splitlines())
assert all(path in expected or path.startswith('docs/exec-plans/evidence/HG-047/') or
           path.startswith('docs/exec-plans/reviews/HG-047/') for path in changed)
protected = [
    'FROZEN_BASELINE.json', 'CURRENT_REQUIREMENT_SET.json', 'src', 'migrations',
    'tests/db', '.github/workflows', 'KineticLoop_Harness_Backlog_v0.2.json',
    'KineticLoop_Harness_Traceability_v0.3.json', 'MILESTONE_CLOSURE.schema.json',
    'docs/exec-plans/active/KL-080.md', 'tools/harness/db_policy.py',
    'tools/harness/db_ci.py', 'tools/harness/github_app.py',
    'tools/harness/gate_validate.py', 'tools/harness/gate_pytest.py',
    'tools/harness/db_ci_pytest.py', 'tools/harness/local_db',
    'tools/harness/run_harness_tests.py', 'tools/harness/parallel_observer.py',
    'tests/harness/test_parallel_runner.py', 'pyproject.toml', 'uv.lock',
]
for identity in ('HG-045', 'HG-046', 'HG-048'):
    protected += [f'docs/exec-plans/{kind}/{identity}' for kind in ('evidence', 'reviews')]
    protected += [f'docs/exec-plans/governance/{identity}.yaml']
frozen = json.loads(git('show', base + ':FROZEN_BASELINE.json'))
protected += [entry['path'] for entry in frozen['files']]
assert not git('diff', '--name-only', base, tested, '--', *protected)
plain = [path for path in changed if not path.startswith('docs/exec-plans/evidence/')]
print(json.dumps({'base': base, 'tested': tested, 'changed_files': sorted(changed),
                  'protected_paths_unchanged': sorted(set(protected)),
                  'source_metadata_bytes': sum(len(git('show', tested + ':' + path)) for path in plain),
                  'source_metadata_blob_hashes': {
                      path: hashlib.sha256(git('show', tested + ':' + path)).hexdigest()
                      for path in sorted(plain)}, 'status': 'PASS'}, indent=2))
