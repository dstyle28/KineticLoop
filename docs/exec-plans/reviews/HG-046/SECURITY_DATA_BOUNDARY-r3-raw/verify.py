"""Bounded independent proof; fixture repositories live only in temporary storage."""
import codecs
import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path('/Users/davetian/.codex/worktrees/ffff/KineticLoop')
HEAD = 'fb720bc37c8e9ec436b0673de71c282f9778e6a8'
BASE = '26906bd7f4444914c228e98377f2b164fee0dd5d'
TESTED = 'fb7d62b73d80a56b8bce1d0f7cbd29f14aff77ab'
REF = 'docs/exec-plans/evidence/HG-046/run.log'

def module(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

ce = module('compact', 'tools/harness/compact_evidence.py')
v = module('validator', 'tools/harness/validate_harness.py')

for check in ['focused', 'harness', 'unit', 'lint', 'typecheck', 'authority', 'source_diff']:
    path = f'docs/exec-plans/evidence/HG-046/selected-fb7d62b/{check}.json'
    manifest_bytes = ce.blob(ROOT, path, HEAD)
    record = json.loads(manifest_bytes)
    raw = ce.read(ROOT, path, HEAD, tested=TESTED, command=record['command'], exit_code=0)
    assert ce.digest(raw) == record['raw_sha256'] and len(raw) == record['raw_bytes']
    if check in ['focused', 'harness', 'unit']:
        count = {'focused': 114, 'harness': 1005, 'unit': 241}[check]
        assert f'{count} passed'.encode() in raw
    print(json.dumps({'selected': check, 'envelope_sha256': ce.digest(manifest_bytes),
                      'raw_sha256': ce.digest(raw), 'raw_bytes': len(raw),
                      'test_counts': record['test_counts'], 'exact_binding': True}))
assert not v.governance_suffix_errors(ROOT, TESTED, HEAD, 'HG-046', 'tested')
audit = ce.audit(ROOT, BASE, HEAD, 'HG-046')
assert not audit['errors']
print(json.dumps({'approved_base_audit': audit, 'tested_suffix': 'valid'}))

def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root).decode().strip()

def commit(root):
    git(root, 'add', '.')
    git(root, 'commit', '-qm', 'isolated evidence fixture')
    return git(root, 'rev-parse', 'HEAD')

bypasses = []
with tempfile.TemporaryDirectory(prefix='hg046-security-r3-') as temporary:
    root = Path(temporary)
    git(root, 'init', '-q')
    git(root, 'config', 'user.name', 'Independent Fixture')
    git(root, 'config', 'user.email', 'fixture@example.invalid')
    (root / 'source').write_bytes(b'fixture')
    base = commit(root)
    record = ce.capture(root, REF.replace('.log', '.json'), b'1 passed in 0.01s\n',
                        base, 'pytest', 1, '2026-10-02T00:00:00Z')
    (root / REF.replace('.log', '.json')).unlink()
    (root / record['payload']).unlink()
    text = json.dumps(record, sort_keys=True, separators=(',', ':'))
    for encoding in ['utf-8-sig', 'utf-16', 'utf-16-le', 'utf-16-be',
                     'utf-32', 'utf-32-le', 'utf-32-be']:
        (root / REF).write_bytes(text.encode(encoding))
        head = commit(root)
        assert not v.evidence_exists(root, REF, head)
    print('Seven standard JSON encodings reject the absent payload.')
    for bom, body_encoding in [(codecs.BOM_UTF16_LE, 'utf-32-le'),
                               (codecs.BOM_UTF16_BE, 'utf-32-be')]:
        raw = bom + text.encode(body_encoding)
        (root / REF).write_bytes(raw)
        head = commit(root)
        try:
            json.loads(raw)
        except (ValueError, UnicodeError) as error:
            json_error = type(error).__name__ + ': ' + str(error)
        else:
            raise AssertionError('Expected malformed BOM/body combination')
        available = v.evidence_exists(root, REF, head, head, 'wrong-command', 0)
        recovered = ce.read(root, REF, head, tested=head, command='wrong-command', exit_code=0)
        report = ce.audit(root, base, head, 'HG-046')
        item = {'fixture_base': base, 'fixture_head': head, 'path': REF,
                'payload_absent': not (root / record['payload']).exists(),
                'recorded_exit': record['exit_code'], 'expected_exit': 0,
                'recorded_tested': base, 'expected_tested': head,
                'recorded_command': 'pytest', 'expected_command': 'wrong-command',
                'prefix_hex': bom.hex(), 'body_encoding': body_encoding,
                'exact_input_hex': raw.hex(), 'input_bytes': len(raw),
                'input_sha256': ce.digest(raw), 'json_loads_error': json_error,
                'body_is_reserved_json': json.loads(raw[len(bom):].decode(body_encoding)) == record,
                'detected_encoding': json.detect_encoding(raw),
                'envelope_outcome': ce.envelope(raw), 'evidence_exists': available,
                'read_equals_exact_input': recovered == raw,
                'read_sha256': ce.digest(recovered), 'audit': report}
        print(json.dumps(item, sort_keys=True))
        if available and recovered == raw and not report['errors']:
            bypasses.append(body_encoding)
assert not bypasses, 'Malformed reserved BOM/body encodings accepted: ' + ', '.join(bypasses)
