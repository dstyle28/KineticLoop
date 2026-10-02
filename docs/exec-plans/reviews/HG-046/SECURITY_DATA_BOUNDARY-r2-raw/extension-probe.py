"""Bounded independent classification probe; isolated Git fixtures only."""
import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path('/Users/davetian/.codex/worktrees/ffff/KineticLoop')
HEAD = '5182feb0ad33319336efd913f63bf8c01c74b6a7'
TESTED = '58de0f7dfbf39947f2c2c1852cc927823e79b4c3'
BASE = '26906bd7f4444914c228e98377f2b164fee0dd5d'
spec = importlib.util.spec_from_file_location('validator', ROOT / 'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
ce = v.compact_evidence

def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root, stderr=subprocess.DEVNULL).decode().strip()

def commit(root):
    git(root, 'add', '.')
    git(root, 'commit', '-qm', 'probe')
    return git(root, 'rev-parse', 'HEAD')

print('reviewed_head', git(ROOT, 'rev-parse', 'HEAD'))
checks = v.load_artifact_at_revision(ROOT, 'docs/exec-plans/governance/HG-046.yaml', HEAD)['checks_run']
for check in checks:
    output = ce.read(ROOT, check['evidence_ref'], HEAD, tested=TESTED, command=check['command'], exit_code=0)
    print(json.dumps({'committed_check': check['check_id'], 'raw_bytes': len(output), 'counts': ce.envelope(ce.blob(ROOT, check['evidence_ref'], HEAD))['test_counts'], 'output': output.decode()}))
print('protected_base_budget', json.dumps(ce.audit(ROOT, BASE, HEAD, 'HG-046'), sort_keys=True))
print('tested_suffix_errors', v.governance_suffix_errors(ROOT, TESTED, HEAD, 'HG-046', 'tested'))
with tempfile.TemporaryDirectory(prefix='hg046-security-r2-', dir='/private/tmp') as directory:
    root = Path(directory)
    git(root, 'init', '-q')
    git(root, 'config', 'user.name', 'Fixture')
    git(root, 'config', 'user.email', 'fixture@example.invalid')
    (root / 'source').write_text('fixture')
    base = commit(root)
    ref = 'docs/exec-plans/evidence/HG-046/run.json'
    record = ce.capture(root, ref, b'1 passed in 0.01s\n', base, 'pytest', 0)
    (root / record['payload']).unlink()
    (root / ref).unlink()
    variants = [('utf-8', suffix) for suffix in ['.log', '.JSON', '']] + [('utf-16', '.json'), ('utf-32', '.log')]
    for encoding, suffix in variants:
        target = root / ('docs/exec-plans/evidence/HG-046/run-' + encoding + suffix)
        target.write_bytes(json.dumps(record).encode(encoding))
    rawref = 'docs/exec-plans/evidence/HG-046/raw-utf16.txt'
    (root / rawref).write_bytes(json.dumps({'nested': [{'raw_utf8': 'copy'}]}).encode('utf-16'))
    revision = commit(root)
    for encoding, suffix in variants:
        path = 'docs/exec-plans/evidence/HG-046/run-' + encoding + suffix
        data = ce.blob(root, path, revision)
        print(json.dumps({'encoding': encoding, 'suffix': suffix, 'json_marker': json.loads(data)['kineticloop_evidence'], 'envelope_classified': ce.envelope(data) is not None, 'missing_payload_evidence_exists': v.evidence_exists(root, path, revision, base, 'pytest', 0)}))
    print('probe_budget', json.dumps(ce.audit(root, base, revision, 'HG-046'), sort_keys=True))
