"""Exact scope/frozen-byte audit; no task/product PASS."""
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]
BASE = 'af09be228fbc89d074b6e863c83e1fdda343d55b'
SPEC = importlib.util.spec_from_file_location('validator', ROOT / 'tools/harness/validate_harness.py')
assert SPEC and SPEC.loader
v = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(v)
EXPECTED = ['tools/harness/compact_evidence.py', 'tools/harness/validate_harness.py',
 'tests/harness/test_compact_evidence.py', 'tests/harness/test_review_evidence_provenance.py',
 'tests/harness/test_m3_milestone_closure.py', 'tests/harness/test_validator.py',
 'tests/harness/test_local_gate.py', 'docs/harness/EVIDENCE_STORAGE_POLICY.md',
 'docs/harness/HARNESS_GOVERNANCE_CONTRACT.md', 'docs/harness/LOCAL_DB_CI.md',
 'tools/harness/README.md', 'CURRENT_DOCUMENT_INDEX.json', 'HARNESS_DOCUMENT_MANIFEST.json',
 'docs/exec-plans/governance/HG-054.yaml', 'docs/exec-plans/evidence/HG-054/**',
 'docs/exec-plans/reviews/HG-054/**']

def main():
    actual = v.governance_allowed_patterns('HG-054')
    assert actual == EXPECTED, 'allowlist differs from packet'
    changed = subprocess.check_output(['git', 'diff', '--name-only', BASE], cwd=ROOT).decode().splitlines()
    untracked = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard'], cwd=ROOT).decode().splitlines()
    assert all(v.matches(p, EXPECTED) for p in changed + untracked), 'undeclared path'
    frozen = json.loads(subprocess.check_output(['git', 'show', BASE + ':FROZEN_BASELINE.json'], cwd=ROOT))
    frozen_paths = ['FROZEN_BASELINE.json']
    def collect(value):
        if isinstance(value, dict):
            if 'path' in value:
                frozen_paths.append(value['path'])
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)
    collect(frozen)
    for path in frozen_paths:
        original = subprocess.check_output(['git', 'show', BASE + ':' + path], cwd=ROOT)
        assert (ROOT / path).read_bytes() == original, 'frozen change:' + path
    print(json.dumps({'base': BASE, 'head': v.resolve(ROOT, 'HEAD'), 'scope': 'PASS',
                      'frozen_paths': sorted(set(frozen_paths)), 'changed': changed,
                      'frozen_baseline_sha256': hashlib.sha256((ROOT / 'FROZEN_BASELINE.json').read_bytes()).hexdigest()}, indent=2))

if __name__ == '__main__':
    main()
