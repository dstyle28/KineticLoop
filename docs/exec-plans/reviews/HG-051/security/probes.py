"""HG051 independent security probes; temporary Git objects only."""
import copy
import importlib.util
import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
REVIEWED = '7141b1dfe48df8f0e25429cf9ff646af6de4b5ce'
BASE = 'b877db0edd2e4550d6ea81750656112fb7f2e223'
TESTED = '5debfe1b41a26c0b3f985917b80995a9eb38b92e'
spec = importlib.util.spec_from_file_location('reviewed_compact', ROOT / 'tools/harness/compact_evidence.py')
ce = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ce)


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root).decode().strip()


def reject(name, action):
    try:
        action()
    except (ValueError, OSError):
        print('REJECT ' + name)
    else:
        raise AssertionError('ACCEPTED ' + name)


assert git(ROOT, 'rev-parse', 'HEAD') == REVIEWED
assert ce.git(ROOT, 'show', REVIEWED + ':tools/harness/compact_evidence.py') == (ROOT / 'tools/harness/compact_evidence.py').read_bytes()
assert ce.git(ROOT, 'show', REVIEWED + ':HISTORICAL_EVIDENCE_MAPPING.schema.json') == (ROOT / 'HISTORICAL_EVIDENCE_MAPPING.schema.json').read_bytes()
assert ce.git(ROOT, 'diff', '--name-only', TESTED, REVIEWED, '--', 'tools', 'tests', 'HISTORICAL_EVIDENCE_MAPPING.schema.json') == b''
print('BOUND reviewed=' + REVIEWED + ' tested=' + TESTED)
assert (ce.PLAIN_LIMIT, ce.STORED_LIMIT, ce.RAW_LIMIT, ce.TOTAL_LIMIT) == (262144, 8388608, 67108864, 16777216)
print('PASS unchanged storage bounds')
originals = ce.historical_originals()
for original in originals:
    raw = ce.archive_original(ROOT, original)
    assert ce.read(ROOT, original['path'], original['revision']) == raw
    assert original['execution']['timestamp'] is None
    ref = original['execution_record']
    ce.verify_historical_ref(ROOT, ref, ref['revision'])
    print('ORIGINAL exact bytes=' + str(len(raw)) + ' sha256=' + ce.digest(raw) + ' outcome=' + original['execution']['result'])
for ref in ce.historical_template()['preserved_records']:
    ce.verify_historical_ref(ROOT, ref, ref['revision'])
print('PASS all original regular blobs and preserved hashed records')

# Decode committed execution evidence at the reviewed SHA, retaining observed exits/counts.
folder = 'docs/exec-plans/evidence/HG-051/final-5debfe1/'
execution = json.loads(ce.blob(ROOT, folder + 'EXECUTION.json', REVIEWED))
for row in execution['executions']:
    ref = folder + row['check_id'] + '.json'
    raw = ce.read(ROOT, ref, REVIEWED, tested=TESTED, command=row['command'], exit_code=row['exit_code'])
    print('CHECK ' + row['check_id'] + ' exit=' + str(row['exit_code']) + ' recovered=' + str(len(raw)))
    if row['check_id'] in {'focused', 'harness', 'unit'}:
        print('OUTPUT ' + raw.decode(errors='replace').splitlines()[-1])
print('PASS committed command/tested/exit bindings')

with tempfile.TemporaryDirectory(prefix='hg051-security-', dir='/private/tmp') as temp:
    root = Path(temp)
    git(root, 'init', '-q')
    git(root, 'config', 'user.name', 'Independent security reviewer')
    git(root, 'config', 'user.email', 'review@example.invalid')
    objects = Path(git(ROOT, 'rev-parse', '--git-path', 'objects')).resolve()
    (root / '.git/objects/info/alternates').write_text(str(objects) + '\n')
    source = '477b213f67429f571b60d5701f02892ab9c1cbbf'
    git(root, 'update-ref', 'HEAD', source)
    git(root, 'read-tree', source)
    for original in originals:
        manifest, payload = ce.archive_envelope(original, ce.archive_original(ROOT, original))
        target = root / original['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(manifest))
        (root / manifest['payload']).write_bytes(payload)
        git(root, 'add', '--', original['path'], manifest['payload'])
    git(root, 'commit', '-qm', 'independent lossless storage probe')
    storage = git(root, 'rev-parse', 'HEAD')
    mapping = ce.archive_mapping(root, storage)
    target = root / ce.MAPPING_PATH
    target.write_text(json.dumps(mapping))
    git(root, 'add', '--', ce.MAPPING_PATH)
    git(root, 'commit', '-qm', 'independent mapping probe')
    revision = git(root, 'rev-parse', 'HEAD')
    assert not ce.archive_audit(root, revision)[0]
    audit = ce.audit(root, source, revision, 'KL-080')
    assert not audit['errors'], audit
    print('PASS actual four-blob roundtrip; total changed storage bytes=' + str(audit['stored_bytes']))
    for original in originals:
        assert ce.read_archive(root, original['path'], revision) == ce.archive_original(ROOT, original)
        reject('archive rejected by ordinary execution reader', lambda: ce.read(root, original['path'], revision))
    for name, action in [
        ('unknown mapping metadata', lambda m: m.update(unapproved=True)),
        ('unknown original metadata', lambda m: m['entries'][0]['original'].update(unapproved=True)),
        ('unknown storage metadata', lambda m: m['entries'][0]['storage'].update(unapproved=True)),
        ('invented timestamp', lambda m: m['entries'][1]['original']['execution'].update(timestamp='now')),
        ('failed source promoted to PASS', lambda m: m['entries'][1]['original']['execution'].update(result='PASS', exit_code=0)),
        ('historical outcome promoted', lambda m: m['historical_outcome'].update(task_status='PASS')),
        ('storage owner traversal', lambda m: m['entries'][0]['storage'].update(payload='../borrow.gz')),
        ('storage revision alias', lambda m: m['entries'][0]['storage'].update(revision='HEAD')),
        ('duplicate entry', lambda m: m['entries'].append(m['entries'][0])),
        ('omitted entry', lambda m: m['entries'].pop()),
    ]:
        changed = copy.deepcopy(mapping)
        action(changed)
        reject(name, lambda: ce.validate_archive(root, changed, revision, verify_originals=True))
    for encoding in ['utf-8', 'utf-16', 'utf-16-le', 'utf-16-be', 'utf-32', 'utf-32-le', 'utf-32-be']:
        for wrapper in [mapping, [mapping], {'wrapped': mapping}]:
            raw = json.dumps(wrapper).encode(encoding)
            reject('capture reserved archival metadata ' + encoding, lambda: ce.capture(root, 'docs/exec-plans/reviews/HG-051/security/probe.json', raw, revision, 'review probe', 0))
    print('PASS encoded/wrapped archive cannot become gzip-v1 execution evidence')
    # Review bytes remain included in aggregate accounting.
    review_path = root / 'docs/exec-plans/reviews/KL-080/security/probe.log'
    review_path.parent.mkdir(parents=True)
    review_path.write_bytes(b'independent review bytes\n')
    git(root, 'add', '--', str(review_path.relative_to(root)))
    git(root, 'commit', '-qm', 'review accounting probe')
    reviewed_suffix = git(root, 'rev-parse', 'HEAD')
    suffix_audit = ce.audit(root, source, reviewed_suffix, 'KL-080')
    assert not suffix_audit['errors']
    assert suffix_audit['stored_bytes'] == audit['stored_bytes'] + len(review_path.read_bytes())
    print('PASS review suffix bytes included')
    original_git = ce.git
    unavailable = {original['revision'] for original in originals}
    def missing_original(root, *args):
        if any(rev + '^{commit}' in args for rev in unavailable):
            raise ValueError('independent-unavailable-original')
        return original_git(root, *args)
    ce.git = missing_original
    assert ce.read_archive(root, originals[0]['path'], revision)
    reject('unavailable original cannot borrow archive', lambda: ce.archive_original(root, originals[0]))
    reject('unavailable original cannot borrow HEAD', lambda: ce.read(root, originals[0]['path'], originals[0]['revision']))
    assert ce.archive_audit(root, revision)[0]
    ce.git = original_git
    print('PASS archive recovery and original execution verification are distinct')
print('PASS independent security probes complete')
