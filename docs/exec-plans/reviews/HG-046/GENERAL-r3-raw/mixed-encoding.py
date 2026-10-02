from pathlib import Path
import importlib.util
import json
import subprocess
import tempfile
ROOT = Path('/Users/davetian/.codex/worktrees/ffff/KineticLoop')
spec = importlib.util.spec_from_file_location('validator', ROOT / 'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
ce = v.compact_evidence
with tempfile.TemporaryDirectory(prefix='hg046-general-r3-', dir='/private/tmp') as tmp:
    root = Path(tmp)
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=root).decode().strip()
    git('init', '-q')
    git('config', 'user.name', 'Fixture')
    git('config', 'user.email', 'fixture@example.invalid')
    (root / 'source').write_text('fixture')
    git('add', '.')
    git('commit', '-qm', 'fixture base')
    base = git('rev-parse', 'HEAD')
    ref = 'docs/exec-plans/evidence/HG-046/run.json'
    record = ce.capture(root, ref, b'1 passed in 0.01s\n', base, 'pytest', 0)
    malformed = b'\xff\xfe' + json.dumps(record).encode('utf-32-le')
    (root / ref).write_bytes(malformed)
    (root / record['payload']).unlink()
    git('add', '.')
    git('commit', '-qm', 'mixed BOM and missing payload')
    head = git('rev-parse', 'HEAD')
    classification = ce.envelope(malformed)
    raw = ce.read(root, ref, head, tested=base, command='wrong-command', exit_code=17)
    available = v.evidence_exists(root, ref, head, base, 'wrong-command', 17)
    audit = ce.audit(root, base, head, 'HG-046')
    print(json.dumps({'probe': 'UTF16LE BOM plus UTF32LE storage body; payload removed', 'classification': classification, 'read_returns_original_malformed_bytes': raw == malformed, 'evidence_exists_with_wrong_command_and_exit': available, 'audit_errors': audit['errors']}, sort_keys=True))
    assert classification is None and raw == malformed and available and not audit['errors'], 'bypass not reproduced'
