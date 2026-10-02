"""Show a clean prospective audit accepting missing-payload alternate JSON encodings."""
import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path
ROOT = Path('/Users/davetian/.codex/worktrees/ffff/KineticLoop')
spec = importlib.util.spec_from_file_location('validator', ROOT / 'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
ce = v.compact_evidence

def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root, stderr=subprocess.DEVNULL).decode().strip()
def commit(root):
    git(root, 'add', '.')
    git(root, 'commit', '-qm', 'encoding fixture')
    return git(root, 'rev-parse', 'HEAD')
for encoding in ('utf-16', 'utf-32'):
    with tempfile.TemporaryDirectory(prefix='hg046-encoding-', dir='/private/tmp') as d:
        root = Path(d)
        git(root, 'init', '-q')
        git(root, 'config', 'user.name', 'Fixture')
        git(root, 'config', 'user.email', 'fixture@example.invalid')
        (root / 'source').write_text('fixture')
        base = commit(root)
        ref = 'docs/exec-plans/evidence/HG-046/run.json'
        record = ce.capture(root, ref, b'actual output\n', base, 'actual command', 1)
        (root / record['payload']).unlink()
        (root / ref).write_bytes(json.dumps(record).encode(encoding))
        head = commit(root)
        report = ce.audit(root, base, head, 'HG-046')
        available = v.evidence_exists(root, ref, head, '0' * 40, 'different command', 0)
        assert available and not report['errors']
        print(json.dumps({'encoding': encoding, 'missing_payload': True, 'mismatched_tested_command_exit_accepted': available, 'audit_errors': report['errors'], 'stored_bytes': report['stored_bytes']}))
