"""Bounded independent committed-proof and malformed-encoding review."""
import codecs
import gzip
import hashlib
import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
HEAD = '02d95c1d86ade83128671190e1e1bf916cfe2b88'
TESTED = '9f2f38fe69f772d1564f0fa5eee2441da038aef1'
BASE = '26906bd7f4444914c228e98377f2b164fee0dd5d'

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value

ce = module('ce', 'tools/harness/compact_evidence.py')
v = module('v', 'tools/harness/validate_harness.py')

def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root)

def regular(root, path, revision):
    entry = git(root, 'ls-tree', '-z', revision, '--', path).split(b'\0')[0]
    meta, actual = entry.split(b'\t')
    mode, kind, oid = meta.split()
    assert actual.decode() == path and mode in (b'100644', b'100755') and kind == b'blob'
    return git(root, 'cat-file', 'blob', oid.decode())

def sha(data):
    return hashlib.sha256(data).hexdigest()

report = {'reviewed_head': HEAD, 'tested_source': TESTED, 'selected': []}
for name in ('focused', 'harness', 'unit', 'lint', 'typecheck', 'authority', 'source_diff', 'base-drift'):
    path = 'docs/exec-plans/evidence/HG-046/selected-9f2f38f/' + name + '.json'
    manifest = json.loads(regular(ROOT, path, HEAD))
    stored = regular(ROOT, manifest['payload'], HEAD)
    raw = gzip.decompress(stored)
    assert len(stored) == manifest['stored_bytes'] and sha(stored) == manifest['stored_sha256']
    assert len(raw) == manifest['raw_bytes'] and sha(raw) == manifest['raw_sha256']
    assert manifest['tested_commit'] == TESTED
    assert manifest['exit_code'] == (1 if name == 'base-drift' else 0)
    assert ce.read(ROOT, path, HEAD, tested=TESTED, command=manifest['command'], exit_code=manifest['exit_code']) == raw
    if name in ('focused', 'harness', 'unit'):
        expected = {'focused': '194 passed', 'harness': '1085 passed', 'unit': '241 passed'}[name]
        assert expected.encode() in raw
    if name == 'authority':
        assert b'HARNESS_CHECK_PASS' in raw and b'HARNESS_CHECK_FAIL' not in raw
    report['selected'].append({'name': name, 'path': path, 'command': manifest['command'], 'exit_code': manifest['exit_code'], 'raw_bytes': len(raw), 'raw_sha256': sha(raw), 'observed_tail': raw.decode(errors='replace')[-180:]})
assert git(ROOT, 'merge-base', '--is-ancestor', BASE, TESTED) == b''
assert git(ROOT, 'merge-base', '--is-ancestor', TESTED, HEAD) == b''
report['tested_suffix_paths'] = git(ROOT, 'diff', '--name-only', TESTED, HEAD).decode().splitlines()
assert all(p == 'docs/exec-plans/governance/HG-046.yaml' or p.startswith('docs/exec-plans/evidence/HG-046/') for p in report['tested_suffix_paths'])
report['budget'] = ce.audit(ROOT, BASE, HEAD, 'HG-046')
assert report['budget']['errors'] == []
assert (ce.PLAIN_LIMIT, ce.STORED_LIMIT, ce.RAW_LIMIT, ce.TOTAL_LIMIT) == (262144, 8388608, 67108864, 16777216)

# Independent original-byte classification probes.
boms = [(codecs.BOM_UTF8, 'utf-8'), (codecs.BOM_UTF16_LE, 'utf-16-le'), (codecs.BOM_UTF16_BE, 'utf-16-be'), (codecs.BOM_UTF32_LE, 'utf-32-le'), (codecs.BOM_UTF32_BE, 'utf-32-be')]
record = {'kineticloop_evidence': 'gzip-v1', 'payload': 'absent', 'stored_sha256': '0' * 64, 'raw_sha256': '0' * 64}
count = 0
for bom, declared in boms:
    for _, body in boms:
        if declared == body:
            continue
        for form in ('literal', 'escaped', 'removed'):
            value = dict(record)
            if form == 'removed':
                value.pop('kineticloop_evidence')
            text = json.dumps(value)
            if form == 'escaped':
                text = text.replace('kineticloop_evidence', 'kineticloop' + chr(92) + 'u005fevidence')
            data = bom + text.encode(body)
            try:
                ce.envelope(data)
            except ValueError:
                count += 1
            else:
                raise AssertionError((declared, body, form))
            assert ce.envelope(bom + 'opaque original bytes'.encode(body)) is None
report['conflicting_original_byte_rejections'] = count

# Commit malformed r3-style bytes under uppercase and extensionless names.
with tempfile.TemporaryDirectory(prefix='hg046-security-r4-', dir='/private/tmp') as temp:
    root = Path(temp)
    git(root, 'init', '-q')
    git(root, 'config', 'user.name', 'Review fixture')
    git(root, 'config', 'user.email', 'review@example.invalid')
    (root / 'source').write_bytes(b'isolated')
    git(root, 'add', '.')
    git(root, 'commit', '-qm', 'base')
    base = git(root, 'rev-parse', 'HEAD').decode().strip()
    ref = 'docs/exec-plans/evidence/HG-046/run.json'
    manifest = ce.capture(root, ref, b'original opaque\xff\0\n', base, 'actual fixture command', 1)
    (root / manifest['payload']).unlink()
    text = json.dumps(manifest)
    (root / ref).unlink()
    paths = []
    for label, bom, body in (('LE.JSON', codecs.BOM_UTF16_LE, 'utf-32-le'), ('BE', codecs.BOM_UTF16_BE, 'utf-32-be')):
        path = str(Path(ref).parent / label)
        (root / path).write_bytes(bom + text.encode(body))
        paths.append(path)
    git(root, 'add', '.')
    git(root, 'commit', '-qm', 'missing payload malformed storage')
    head = git(root, 'rev-parse', 'HEAD').decode().strip()
    results = []
    for path in paths:
        try:
            ce.read(root, path, head, tested=head, command='wrong command', exit_code=0)
        except ValueError as error:
            rejection = str(error)
        else:
            raise AssertionError('read accepted malformed storage')
        assert not v.evidence_exists(root, path, head, head, 'wrong command', 0)
        results.append({'path': path, 'original_sha256': sha((root/path).read_bytes()), 'read_rejection': rejection, 'availability': False})
    budget = ce.audit(root, base, head, 'HG-046')
    assert len(budget['errors']) == len(paths)
    report['committed_adversarial'] = {'cases': results, 'audit_errors': budget['errors']}
report['scope'] = 'Assigned protected base only; no broad tests, authority rerun or merge recommendation.'
print(json.dumps(report, indent=2))
