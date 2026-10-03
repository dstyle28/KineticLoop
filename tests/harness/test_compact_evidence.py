"""Isolated Git security/provenance and prospective budget tests."""
import codecs
import gzip
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('compact', ROOT / 'tools/harness/compact_evidence.py')
assert SPEC and SPEC.loader
ce = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ce)
SPEC_V = importlib.util.spec_from_file_location('validator', ROOT / 'tools/harness/validate_harness.py')
assert SPEC_V and SPEC_V.loader
v = importlib.util.module_from_spec(SPEC_V)
SPEC_V.loader.exec_module(v)
REF = 'docs/exec-plans/evidence/HG-047/run.json'


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root).decode().strip()


def commit(root):
    git(root, 'add', '.')
    git(root, 'commit', '-qm', 'fixture')
    return git(root, 'rev-parse', 'HEAD')


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, 'init', '-q')
    git(tmp_path, 'config', 'user.name', 'Fixture')
    git(tmp_path, 'config', 'user.email', 'fixture@example.invalid')
    (tmp_path / 'source').write_text('fixture')
    base = commit(tmp_path)
    return tmp_path, base


def captured(repo, raw=b'1 passed in 0.01s\n'):
    root, base = repo
    record = ce.capture(root, REF, raw, base, 'pytest', 0, '2026-10-02T00:00:00Z')
    head = commit(root)
    return root, base, record, head


def replace_record(root, record):
    (root / REF).write_text(json.dumps(record))
    return commit(root)


def test_exact_retrieval_and_deterministic_capture(repo):
    raw = b'\xff\0' + bytes(range(256)) * 100 + b'1 passed\n'
    root, base, record, head = captured(repo, raw)
    assert ce.read(root, REF, head, tested=base, command='pytest', exit_code=0) == raw
    assert (root / record['payload']).read_bytes() == gzip.compress(raw, compresslevel=9, mtime=0)
    assert record['raw_bytes'] == len(raw)
    assert record['raw_sha256'] == ce.digest(raw)
    assert ce.audit(root, base, head, 'HG-047')['errors'] == []
    assert v.evidence_exists(root, REF, head, base, 'pytest', 0)
    assert v.m3_evidence_bytes(root, {'path': REF, 'revision': head,
                                    'sha256': ce.digest((root / REF).read_bytes())}, head) == raw


@pytest.mark.parametrize('field,value', [
    ('stored_sha256', '0' * 64), ('raw_sha256', '0' * 64),
    ('stored_bytes', 1), ('raw_bytes', 1), ('raw_bytes', -1),
    ('raw_bytes', ce.RAW_LIMIT + 1), ('stored_bytes', ce.STORED_LIMIT + 1),
    ('raw_bytes', True), ('kineticloop_evidence', 'tar-v1'),
    ('payload', 'docs/exec-plans/evidence/HG-045/borrow.gz'),
    ('payload', '../borrow.gz'), ('payload', '/tmp/borrow.gz'),
    ('payload', 'docs/exec-plans/evidence/HG-047/a/../borrow.gz'),
    ('tested_commit', '0' * 40), ('raw_utf8', '1 passed'),
])
def test_manifest_tamper_fails(repo, field, value):
    root, base, record, _ = captured(repo)
    record[field] = value
    head = replace_record(root, record)
    assert not v.evidence_exists(root, REF, head, base, 'pytest', 0)
    assert ce.audit(root, base, head, 'HG-047')['errors']


@pytest.mark.parametrize('mutation', ['missing', 'tamper', 'symlink', 'directory'])
def test_payload_requires_exact_regular_git_blob(repo, mutation):
    root, base, record, original = captured(repo)
    path = root / record['payload']
    path.unlink()
    if mutation == 'tamper':
        path.write_bytes(b'corrupt')
    elif mutation == 'symlink':
        path.symlink_to(root / 'source')
    elif mutation == 'directory':
        path.mkdir()
        (path / 'entry').write_text('not a blob')
    head = commit(root)
    assert not v.evidence_exists(root, REF, head)
    assert ce.read(root, REF, original) == b'1 passed in 0.01s\n'
    assert not v.review_evidence_exists(root, REF, head, original, 'HG-047', True)


@pytest.mark.parametrize('raw,stored', [
    (b'a' * 1000000, gzip.compress(b'a' * 1000000, mtime=0)),
    (b'a', gzip.compress(b'a', mtime=0) + gzip.compress(b'b', mtime=0)),
    (b'a', gzip.compress(b'a', mtime=0) + b'trailing'),
    (b'a', gzip.compress(b'a', mtime=0)[:-4]),
], ids=['raw-size-bound', 'concatenated-members', 'trailing-bytes', 'truncated-member'])
def test_bounded_single_member_decoder(repo, raw, stored):
    root, _, record, _ = captured(repo, b'a')
    (root / record['payload']).write_bytes(stored)
    record.update(stored_bytes=len(stored), stored_sha256=ce.digest(stored), raw_bytes=1)
    head = replace_record(root, record)
    with pytest.raises(ValueError):
        ce.read(root, REF, head)


def test_revision_command_and_exit_binding(repo):
    root, base, _, head = captured(repo)
    for kwargs in ({'tested': head}, {'command': 'other'}, {'exit_code': 1}):
        with pytest.raises(ValueError):
            ce.read(root, REF, head, **kwargs)
    with pytest.raises(ValueError):
        ce.read(root, REF, base)
    record = json.loads((root / REF).read_text())
    record['tested_commit'] = head
    head2 = replace_record(root, record)
    assert not v.evidence_exists(root, REF, head2, base)


def test_review_created_payload_uses_same_record_revision(repo):
    root, base = repo
    ref = REF.replace('/evidence/', '/reviews/')
    record = ce.capture(root, ref, b'1 passed\n', base, 'pytest', 0)
    head = commit(root)
    assert v.review_evidence_exists(root, ref, base, head, 'HG-047', True)
    assert not v.review_evidence_exists(root, ref, base, head, 'HG-047', False)
    assert not v.review_evidence_exists(root, ref, base, head, 'HG-045', True)
    (root / record['payload']).unlink()
    later = commit(root)
    assert not v.review_evidence_exists(root, ref, base, later, 'HG-047', True)
    assert v.review_evidence_exists(root, ref, base, head, 'HG-047', True)


@pytest.mark.parametrize('path', ['../x', '/tmp/x', 'a//b', 'a/./b', 'a\\b', 'a\0b'])
def test_invalid_paths(repo, path):
    with pytest.raises(ValueError):
        ce.read(repo[0], path, repo[1])


def test_local_and_capture_symlinks_rejected(repo):
    root, base = repo
    directory = root / 'docs/exec-plans/evidence'
    directory.parent.mkdir(parents=True)
    directory.symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError):
        ce.capture(root, REF, b'raw', base, 'pytest', 0)
    assert not v.evidence_exists(root, REF)


def test_plain_history_retained_and_budget_is_prospective(repo):
    root, _ = repo
    directory = root / 'docs/exec-plans/evidence/HG-047'
    directory.mkdir(parents=True)
    raw = b'old' * ce.PLAIN_LIMIT
    (directory / 'old.log').write_bytes(raw)
    old = commit(root)
    (root / 'source').write_text('changed')
    head = commit(root)
    assert ce.read(root, str((directory / 'old.log').relative_to(root)), head) == raw
    assert ce.audit(root, old, head, 'HG-047')['errors'] == []
    (directory / 'old.log').write_bytes(raw + b'new')
    head2 = commit(root)
    assert any('evidence-size' in s for s in ce.audit(root, old, head2, 'HG-047')['errors'])


@pytest.mark.parametrize('filename,data,error', [
    ('a.log', b'x' * (ce.PLAIN_LIMIT + 1), 'evidence-size'),
    ('complete-diff.patch', b'patch', 'full-diff-copy'),
    ('a.json', b'{"nested":[{"raw_utf8":"copy"}]}', 'embedded-raw_utf8'),
    ('a.log', b'{"nested":[{"raw_utf8":"copy"}]}', 'embedded-raw_utf8'),
    ('a.txt', b'{"nested":[{"raw_utf8":"copy"}]}', 'embedded-raw_utf8'),
    ('orphan.gz', b'not compressed', 'unreferenced-payload'),
], ids=['plain-size-limit', 'full-diff-copy', 'embedded-json', 'embedded-log',
        'embedded-text', 'orphan-payload'])
def test_budget_rejects_bulk_and_duplicate_metadata(repo, filename, data, error):
    root, base = repo
    target = root / REF
    target.parent.mkdir(parents=True)
    (target.parent / filename).write_bytes(data)
    head = commit(root)
    assert any(error in e for e in ce.audit(root, base, head, 'HG-047')['errors'])


def test_duplicate_bulk_not_repeated_log_lines(repo):
    root, base = repo
    raw = b'repeated real log line\n' * 1000
    captured(repo, raw)
    target = root / REF
    (target.parent / 'copy.log').write_bytes(raw)
    head = commit(root)
    assert any('duplicate-bulk' in e for e in ce.audit(root, base, head, 'HG-047')['errors'])
    assert ce.read(root, REF, head) == raw


def test_total_budget_and_foreign_history(repo, monkeypatch):
    root, _ = repo
    foreign = root / 'docs/exec-plans/evidence/HG-045/large.log'
    foreign.parent.mkdir(parents=True)
    foreign.write_bytes(b'x' * 1000)
    base = commit(root)
    target = root / REF
    target.parent.mkdir(parents=True)
    for n in range(3):
        (target.parent / f'{n}.log').write_bytes(bytes([n]) * 100)
    head = commit(root)
    monkeypatch.setattr(ce, 'TOTAL_LIMIT', 250)
    report = ce.audit(root, base, head, 'HG-047')
    assert report['stored_bytes'] == 300
    assert any('PR-evidence-total' in e for e in report['errors'])
    # Scope rejects unauthorized foreign writes separately; the budget still
    # counts changed foreign artifacts instead of allowing an identity escape.
    foreign.write_bytes(b'y' * 1000)
    later = commit(root)
    assert ce.audit(root, base, later, 'HG-047')['stored_bytes'] == 1300


def test_duplicate_manifest_keys_reject(repo):
    root, _, _, _ = captured(repo)
    path = root / REF
    path.write_text(path.read_text().replace('"exit_code": 0', '"exit_code": 0, "exit_code": 0'))
    head = commit(root)
    assert not v.evidence_exists(root, REF, head)


def test_stored_size_checked_before_blob_read(repo):
    root, _, record, _ = captured(repo)
    path = root / record['payload']
    with path.open('wb') as stream:
        stream.truncate(ce.STORED_LIMIT + 1)
    head = commit(root)
    with pytest.raises(ValueError, match='evidence-size'):
        ce.read(root, REF, head)


def test_reference_at_wrong_revision_cannot_borrow_payload_from_head(repo):
    root, base, record, original = captured(repo)
    payload = root / record['payload']
    saved = payload.read_bytes()
    payload.unlink()
    missing = commit(root)
    payload.write_bytes(saved)
    restored = commit(root)
    assert ce.read(root, REF, restored) == ce.read(root, REF, original)
    assert not v.evidence_exists(root, REF, missing, base, 'pytest', 0)


def test_invalid_capture_leaves_no_evidence(repo):
    root, _ = repo
    with pytest.raises(ValueError):
        ce.capture(root, REF, b'raw', '0' * 40, 'pytest', 0)
    assert not (root / 'docs').exists()


def test_escaped_marker_cannot_disguise_missing_payload(repo):
    root, _, record, _ = captured(repo)
    path = root / REF
    path.write_text(path.read_text().replace('kineticloop_evidence', 'kineticloop\\u005fevidence'))
    (root / record['payload']).unlink()
    head = commit(root)
    assert not v.evidence_exists(root, REF, head)


def test_compressed_full_diff_cannot_bypass_name_rule(repo):
    root, base, _, head = captured(repo, b'diff --git a/source b/source\n--- a/source\n+++ b/source\n')
    assert any('full-diff-copy' in e for e in ce.audit(root, base, head, 'HG-047')['errors'])


def test_truncated_envelope_does_not_become_plain_proof(repo):
    root, _, _, _ = captured(repo)
    path = root / REF
    path.write_bytes(path.read_bytes()[:-3])
    head = commit(root)
    assert not v.evidence_exists(root, REF, head)


@pytest.mark.parametrize('mutation', ['removed', 'renamed'])
def test_damaged_marker_does_not_turn_manifest_into_plain_proof(repo, mutation):
    root, _, record, _ = captured(repo)
    if mutation == 'removed':
        record.pop('kineticloop_evidence')
    else:
        record['damaged_marker'] = record.pop('kineticloop_evidence')
    head = replace_record(root, record)
    assert not v.evidence_exists(root, REF, head)


def test_unmarked_opaque_historical_json_bytes_remain_lossless(repo):
    root, _ = repo
    path = root / REF
    path.parent.mkdir(parents=True)
    raw = b'opaque historical \\u005f text, not JSON\xff\n'
    path.write_bytes(raw)
    head = commit(root)
    assert ce.read(root, REF, head) == raw
    assert v.evidence_exists(root, REF, head)


def test_symbolic_revision_is_frozen_for_manifest_and_payload(repo, monkeypatch):
    root, _, record, _ = captured(repo)
    payload = root / record['payload']
    saved = payload.read_bytes()
    payload.unlink()
    missing = commit(root)
    payload.write_bytes(saved)
    restored = commit(root)
    git(root, 'update-ref', 'refs/heads/moving', missing)
    original = ce.git
    def advance_after_resolution(root, *args):
        result = original(root, *args)
        if args == ('rev-parse', '--verify', '--end-of-options', 'moving^{commit}'):
            git(root, 'update-ref', 'refs/heads/moving', restored)
        return result
    monkeypatch.setattr(ce, 'git', advance_after_resolution)
    with pytest.raises(ValueError, match='evidence-missing'):
        ce.read(root, REF, 'moving')


@pytest.mark.parametrize('extension', ['log', 'txt', 'opaque'])
@pytest.mark.parametrize('mutation', ['missing', 'tampered'])
def test_renamed_envelope_keeps_metadata_and_payload_guards(repo, extension, mutation):
    root, base, record, _ = captured(repo)
    renamed = REF.removesuffix('json') + extension
    (root / REF).rename(root / renamed)
    head = commit(root)
    assert ce.read(root, renamed, head) == b'1 passed in 0.01s\n'
    assert v.evidence_exists(root, renamed, head, base, 'pytest', 0)
    assert not v.evidence_exists(root, renamed, head, head, 'pytest', 0)
    assert not v.evidence_exists(root, renamed, head, base, 'other-command', 0)
    assert not v.evidence_exists(root, renamed, head, base, 'pytest', 1)
    assert not ce.audit(root, base, head, 'HG-047')['errors']
    payload = root / record['payload']
    if mutation == 'missing':
        payload.unlink()
    else:
        payload.write_bytes(b'not the recorded gzip bytes')
    bad = commit(root)
    assert not v.evidence_exists(root, renamed, bad, base, 'pytest', 0)
    assert ce.audit(root, base, bad, 'HG-047')['errors']


ENCODINGS = ['utf-8-sig', 'utf-16', 'utf-16-le', 'utf-16-be',
             'utf-32', 'utf-32-le', 'utf-32-be']


@pytest.mark.parametrize('encoding', ENCODINGS)
@pytest.mark.parametrize('extension', ['json', 'log'])
@pytest.mark.parametrize('mutation', ['none', 'missing', 'truncated'])
def test_encoded_envelope_keeps_payload_and_metadata_guards(repo, encoding, extension, mutation):
    root, base, record, _ = captured(repo)
    path = REF.removesuffix('json') + extension
    (root / REF).unlink()
    encoded = json.dumps(record).encode(encoding)
    if mutation == 'truncated':
        encoded = encoded[:-3]
    (root / path).write_bytes(encoded)
    if mutation == 'missing':
        (root / record['payload']).unlink()
    head = commit(root)
    if mutation == 'none':
        assert ce.read(root, path, head) == b'1 passed in 0.01s\n'
        assert v.evidence_exists(root, path, head, base, 'pytest', 0)
        assert not v.evidence_exists(root, path, head, head, 'pytest', 0)
        assert not v.evidence_exists(root, path, head, base, 'other-command', 0)
        assert not v.evidence_exists(root, path, head, base, 'pytest', 1)
        assert not ce.audit(root, base, head, 'HG-047')['errors']
    else:
        assert not v.evidence_exists(root, path, head, base, 'pytest', 0)
        assert ce.audit(root, base, head, 'HG-047')['errors']


@pytest.mark.parametrize('encoding', ENCODINGS)
def test_opaque_historical_encoded_bytes_are_not_transcoded(repo, encoding):
    root, _ = repo
    path = root / REF
    path.parent.mkdir(parents=True)
    raw = 'opaque historical \\u005f text, not JSON\n'.encode(encoding) + b'\xff'
    path.write_bytes(raw)
    head = commit(root)
    assert ce.read(root, REF, head) == raw
    assert v.evidence_exists(root, REF, head)


@pytest.mark.parametrize('encoding', ['utf-16-le', 'utf-32-le'])
def test_invalid_encoded_manifest_never_accepts_replacement_text(repo, encoding):
    root, _, record, _ = captured(repo)
    invalid = b'\x00\xd8' if encoding == 'utf-16-le' else b'\x00\x00\x11\x00'
    encoded = json.dumps(record).encode(encoding)
    encoded = encoded.replace('2026'.encode(encoding), invalid + '026'.encode(encoding))
    (root / REF).write_bytes(encoded)
    head = commit(root)
    assert not v.evidence_exists(root, REF, head)


@pytest.mark.parametrize('wrapper', ['list', 'dict'])
@pytest.mark.parametrize('encoding', ['utf-8', 'utf-16'])
def test_wrapped_storage_object_cannot_be_plain_proof(repo, wrapper, encoding):
    root, base, record, _ = captured(repo)
    value = [record] if wrapper == 'list' else {'wrapped': record}
    (root / REF).write_bytes(json.dumps(value).encode(encoding))
    (root / record['payload']).unlink()
    head = commit(root)
    assert not v.evidence_exists(root, REF, head)
    assert ce.audit(root, base, head, 'HG-047')['errors']


BOM_ENCODINGS = [(codecs.BOM_UTF8, 'utf-8'),
                 (codecs.BOM_UTF16_LE, 'utf-16-le'),
                 (codecs.BOM_UTF16_BE, 'utf-16-be'),
                 (codecs.BOM_UTF32_LE, 'utf-32-le'),
                 (codecs.BOM_UTF32_BE, 'utf-32-be')]
CONFLICTING_ENCODINGS = [(bom, body) for bom, declared in BOM_ENCODINGS
                        for _, body in BOM_ENCODINGS if body != declared]


@pytest.mark.parametrize('bom,body', CONFLICTING_ENCODINGS)
@pytest.mark.parametrize('marker_form', ['literal', 'escaped', 'removed'])
def test_conflicting_bom_body_cannot_hide_reserved_storage(repo, bom, body, marker_form):
    root, base, record, _ = captured(repo)
    if marker_form == 'removed':
        record.pop('kineticloop_evidence')
    text = json.dumps(record)
    if marker_form == 'escaped':
        text = text.replace('kineticloop_evidence', 'kineticloop\\u005fevidence')
    raw = bom + text.encode(body)
    with pytest.raises(ValueError):
        ce.envelope(raw)
    (root / REF).write_bytes(raw)
    (root / record['payload']).unlink()
    head = commit(root)
    with pytest.raises(ValueError):
        ce.read(root, REF, head)
    assert not v.evidence_exists(root, REF, head, base, 'pytest', 0)
    assert not v.evidence_exists(root, REF, head, head, 'wrong-command', 1)
    assert ce.audit(root, base, head, 'HG-047')['errors']


@pytest.mark.parametrize('bom,body', CONFLICTING_ENCODINGS)
def test_conflicting_encoding_without_reserved_content_stays_opaque(repo, bom, body):
    root, _ = repo
    path = root / REF
    path.parent.mkdir(parents=True)
    raw = bom + 'opaque historical \\u005f text, not JSON\n'.encode(body)
    path.write_bytes(raw)
    head = commit(root)
    assert ce.read(root, REF, head) == raw
    assert v.evidence_exists(root, REF, head)


def test_validation_session_reuses_only_complete_successful_proof(repo, monkeypatch):
    root, base, record, head = captured(repo)
    original = ce.git
    calls = []
    # The validator owns its separately loaded decoder module.
    def counted(root, *args):
        calls.append(args)
        return original(root, *args)
    monkeypatch.setattr(v.compact_evidence, 'git', counted)
    with v.evidence_validation_session():
        assert v.evidence_exists(root, REF, head, base, 'pytest', 0)
        first = len(calls)
        assert first == 7  # One envelope/payload read with all integrity/ancestry checks.
        for _ in range(20):
            assert v.evidence_exists(root, REF, head, base, 'pytest', 0)
        assert len(calls) == first
        for tested, command, status in ((head, 'pytest', 0), (base, 'other', 0),
                                        (base, 'pytest', 1)):
            assert not v.evidence_exists(root, REF, head, tested, command, status)
        assert len(calls) > first
    before = len(calls)
    with v.evidence_validation_session():
        assert v.evidence_exists(root, REF, head, base, 'pytest', 0)
    assert len(calls) == before + first
    assert v._evidence_verdicts.get() is None


def test_validation_session_never_caches_working_files_or_head(repo):
    root, base, record, head = captured(repo)
    with v.evidence_validation_session():
        assert v.evidence_exists(root, REF)
        assert v.evidence_exists(root, REF, 'HEAD')
        (root / record['payload']).write_bytes(b'corrupt')
        assert not v.evidence_exists(root, REF)
        commit(root)
        assert not v.evidence_exists(root, REF, 'HEAD')
        # The earlier immutable revision continues to supply its own exact bytes.
        assert v.evidence_exists(root, REF, head)


@pytest.mark.parametrize('mutation', ['missing', 'corrupt'])
def test_new_validation_operation_observes_object_loss_and_corruption(repo, mutation):
    root, base, record, head = captured(repo)
    oid = git(root, 'rev-parse', head + ':' + record['payload'])
    path = root / '.git/objects' / oid[:2] / oid[2:]
    original = path.read_bytes()
    with v.evidence_validation_session():
        assert v.evidence_exists(root, REF, head)
    if mutation == 'missing':
        path.unlink()
    else:
        path.unlink()
        path.write_bytes(b'corrupt git object')
    with v.evidence_validation_session():
        assert not v.evidence_exists(root, REF, head)
        # Failed reads never populate a negative cache; an exact restored object
        # must be inspected again even in the same validation operation.
        path.write_bytes(original)
        assert v.evidence_exists(root, REF, head)


def test_validation_cache_binds_repository_path_and_owner(repo):
    root, base, record, head = captured(repo)
    borrowed = 'docs/exec-plans/evidence/HG-048/borrowed.json'
    target = root / borrowed
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(record))
    head = commit(root)
    clone = root.parent / (root.name + '-clone')
    git(root, 'clone', '-q', '--no-hardlinks', str(root), str(clone))
    oid = git(clone, 'rev-parse', head + ':' + record['payload'])
    (clone / '.git/objects' / oid[:2] / oid[2:]).unlink()
    with v.evidence_validation_session():
        assert v.evidence_exists(root, REF, head, base, 'pytest', 0)
        assert not v.evidence_exists(root, borrowed, head, base, 'pytest', 0)
        assert not v.evidence_exists(clone, REF, head, base, 'pytest', 0)


def test_validation_session_is_bounded_nested_and_cleared_on_error(repo, monkeypatch):
    root, base, record, head = captured(repo)
    refs = [REF]
    for i in range(3):
        ref = str(Path(REF).with_name(f'run-{i}.json'))
        (root / ref).write_text(json.dumps(record))
        refs.append(ref)
    head = commit(root)
    monkeypatch.setattr(v, 'EVIDENCE_VERDICT_LIMIT', 2)
    with pytest.raises(RuntimeError):
        with v.evidence_validation_session():
            outer = v._evidence_verdicts.get()
            for ref in refs:
                assert v.evidence_exists(root, ref, head)
                assert len(outer) <= 2
            with v.evidence_validation_session():
                assert v._evidence_verdicts.get() is outer
            raise RuntimeError('interrupted validation')
    assert v._evidence_verdicts.get() is None


def unchecked_storage(root, path, raw, tested, command='pytest'):
    """Construct attacker-controlled storage without the safe capture writer."""
    stored = gzip.compress(raw, mtime=0)
    payload = str(Path(path).parent / (ce.digest(raw) + '.gz'))
    record = {ce.MARKER: ce.FORMAT, 'payload': payload,
              'stored_sha256': ce.digest(stored), 'stored_bytes': len(stored),
              'raw_sha256': ce.digest(raw), 'raw_bytes': len(raw),
              'tested_commit': tested, 'command': command, 'exit_code': 0,
              'timestamp': '1 passed in 0.1s', 'test_counts': {'passed': 1}}
    (root / payload).write_bytes(stored)
    (root / path).write_text(json.dumps(record))


@pytest.mark.parametrize('encoding', ['utf-8', 'utf-16', 'utf-32'])
@pytest.mark.parametrize('mutation', [
    'missing', 'corrupt', 'command', 'tested', 'exit', 'list', 'dict', 'truncated',
])
def test_decoded_reserved_storage_cannot_bypass_direct_rejection(repo, encoding, mutation):
    root, base, record, previous = captured(repo, b'1 skipped\n')
    record['timestamp'] = '1 passed in 0.1s'
    payload = root / record['payload']
    if mutation == 'missing':
        payload.unlink()
    elif mutation == 'corrupt':
        payload.write_bytes(b'corrupt')
    elif mutation in ('command', 'tested', 'exit'):
        field, value = {'command': ('command', 'other'), 'tested': ('tested_commit', previous),
                        'exit': ('exit_code', 1)}[mutation]
        record[field] = value
    value = [record] if mutation == 'list' else {'wrapped': record} if mutation == 'dict' else record
    raw = json.dumps(value).encode(encoding)
    if mutation == 'truncated':
        raw = raw[:-3]
    (root / REF).write_bytes(raw)
    outer = str(Path(REF).with_name('outer.json'))
    unchecked_storage(root, outer, raw, base)
    head = commit(root)
    for ref in (REF, outer):
        with pytest.raises(ValueError):
            ce.read(root, ref, head, tested=base, command='pytest', exit_code=0)
        assert not v.evidence_exists(root, ref, head, base, 'pytest', 0)
    errors = ce.audit(root, base, head, 'HG-047')['errors']
    assert any(error.startswith(outer + ':evidence-') for error in errors), errors


def test_even_valid_nested_storage_is_rejected_and_capture_cleans_up(repo):
    root, base, _, head = captured(repo, b'1 skipped\n')
    raw = (root / REF).read_bytes()
    assert ce.read(root, REF, head) == b'1 skipped\n'
    output = str(Path(REF).parent / 'new/nested.json')
    with pytest.raises(ValueError, match='evidence-nested-envelope'):
        ce.capture(root, output, raw, base, 'pytest', 0)
    assert list((root / output).parent.iterdir()) == []
    outer = str(Path(REF).with_name('outer.json'))
    unchecked_storage(root, outer, raw, base)
    head = commit(root)
    with pytest.raises(ValueError, match='evidence-nested-envelope'):
        ce.read(root, outer, head)


@pytest.mark.parametrize('encoding', ['utf-8', 'utf-16', 'utf-32'])
def test_nonreserved_encoded_raw_is_lossless_in_plain_and_compact_forms(repo, encoding):
    raw = json.dumps({'events': [{'payload': 'ordinary command data'}],
                      'stdout': '1 passed in 0.1s'}).encode(encoding)
    root, base, _, _ = captured(repo, raw)
    plain = str(Path(REF).with_name('ordinary.log'))
    (root / plain).write_bytes(raw)
    head = commit(root)
    for ref in (REF, plain):
        assert ce.read(root, ref, head, tested=base, command='pytest', exit_code=0) == raw
        assert v.evidence_exists(root, ref, head, base, 'pytest', 0)


@pytest.fixture
def archival(repo, monkeypatch):
    """Four small synthetic authorized blobs; production inventory stays exact."""
    import copy
    root, _ = repo
    schema = copy.deepcopy(ce.historical_schema())
    originals = [x['properties']['original']['const'] for x in
                 schema['properties']['entries']['prefixItems']]
    raws = [b'original failed suite: 105 passed, 1 failed\n' + bytes([i]) * 100
            for i in range(4)]
    for original, raw in zip(originals, raws, strict=True):
        target = root / original['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    (root / 'docs/exec-plans/evidence/KL-080/ordinary.log').write_bytes(b'unchanged')
    old = commit(root)
    for original, raw in zip(originals, raws, strict=True):
        original.update(revision=old, blob_id=git(root, 'rev-parse', old + ':' + original['path']),
                        raw_sha256=ce.digest(raw), raw_bytes=len(raw))
        original['execution_record'] = dict(path='source', revision=old,
                                           sha256=ce.digest(b'fixture'), bytes=7)
    schema['properties']['preserved_records']['const'] = [dict(
        path='source', revision=old, sha256=ce.digest(b'fixture'), bytes=7)] * 2
    monkeypatch.setattr(ce, 'historical_schema', lambda: schema)
    # Validator dynamically loads the module separately; use the same authority fixture.
    monkeypatch.setattr(v.compact_evidence, 'historical_schema', lambda: schema)
    for original, raw in zip(originals, raws, strict=True):
        manifest, stored = ce.archive_envelope(original, raw)
        (root / original['path']).write_text(json.dumps(manifest))
        (root / manifest['payload']).write_bytes(stored)
    storage = commit(root)
    mapping = ce.archive_mapping(root, storage)
    (root / ce.MAPPING_PATH).write_text(json.dumps(mapping))
    head = commit(root)
    return root, old, storage, mapping, head, raws


def test_archive_separate_retrieval_original_proof_and_budget(archival):
    root, old, storage, mapping, head, raws = archival
    for entry, raw in zip(mapping['entries'], raws, strict=True):
        original = entry['original']
        assert ce.read(root, original['path'], old) == raw
        assert ce.archive_original(root, original) == raw
        assert ce.read_archive(root, original['path'], head) == raw
        with pytest.raises(ValueError):
            ce.read(root, original['path'], head)
        assert not v.evidence_exists(root, original['path'], head)
        assert not v.review_evidence_exists(root, original['path'], head, head, 'KL-080', True)
        with pytest.raises(ValueError):
            v.m3_evidence_bytes(root, {'path': original['path'], 'revision': head,
                                      'sha256': entry['storage']['envelope_sha256']}, head)
    assert ce.archive_audit(root, head)[0] == []
    report = ce.audit(root, old, head, 'KL-080')
    assert report['errors'] == []
    expected = sum(len(ce.blob(root, p, head)) for p in git(
        root, 'diff', '--no-renames', '--name-only', old, head).splitlines())
    assert report['stored_bytes'] == expected  # mapping/envelopes/payloads all count
    assert ce.audit(root, old, head, 'HG-051')['errors']
    assert not v.evidence_exists(root, ce.MAPPING_PATH, head)
    assert storage != head


@pytest.mark.parametrize('field,value', [
    ('task_identity', 'harness-backlog-v0.2/KL-079'), ('path', '../borrow'),
    ('revision', '0' * 40), ('blob_id', '0' * 40),
    ('raw_sha256', '0' * 64), ('raw_bytes', 1),
])
def test_archive_original_fields_cannot_be_rebound(archival, field, value):
    import copy
    root, _, _, mapping, head, _ = archival
    mapping = copy.deepcopy(mapping)
    mapping['entries'][0]['original'][field] = value
    with pytest.raises(ValueError, match='archive-mapping-schema'):
        ce.validate_archive(root, mapping, head)
    with pytest.raises(ValueError):
        ce.archive_original(root, mapping['entries'][0]['original'])


@pytest.mark.parametrize('field,value', [('exit_code', 0), ('result', 'PASS'),
                                        ('tested_commit', '0' * 40), ('command', 'other'),
                                        ('timestamp', 'invented')])
def test_archive_failed_execution_metadata_cannot_be_promoted(archival, field, value):
    import copy
    root, _, _, mapping, head, _ = archival
    mapping = copy.deepcopy(mapping)
    mapping['entries'][1]['original']['execution'][field] = value
    with pytest.raises(ValueError, match='archive-mapping-schema'):
        ce.validate_archive(root, mapping, head)


@pytest.mark.parametrize('field,value', [('task_status', 'PASS'), ('task_checks_status', 'PASS'),
                                        ('integration_status', 'MERGED'), ('review_status', 'PASS')])
def test_archive_historical_failure_is_immutable(archival, field, value):
    import copy
    root, _, _, mapping, head, _ = archival
    mapping = copy.deepcopy(mapping)
    mapping['historical_outcome'][field] = value
    with pytest.raises(ValueError, match='archive-mapping-schema'):
        ce.validate_archive(root, mapping, head)


@pytest.mark.parametrize('field,value', [
    ('revision', '0' * 40), ('revision', 'HEAD'), ('envelope_path', '../borrow'),
    ('envelope_path', 'docs/exec-plans/evidence/KL-079/file'),
    ('payload', '../borrow.gz'), ('envelope_sha256', '0' * 64), ('envelope_bytes', 1),
    ('payload_sha256', '0' * 64), ('payload_bytes', 1),
    ('payload_bytes', ce.STORED_LIMIT + 1), ('envelope_bytes', ce.PLAIN_LIMIT + 1),
])
def test_archive_storage_tampering(archival, field, value):
    import copy
    root, _, _, mapping, head, _ = archival
    mapping = copy.deepcopy(mapping)
    mapping['entries'][0]['storage'][field] = value
    with pytest.raises(ValueError):
        ce.validate_archive(root, mapping, head)


@pytest.mark.parametrize('mutation', ['missing-map', 'duplicate', 'omitted', 'foreign-map',
                                     'extra-envelope', 'deleted-original', 'nonmigrated'])
def test_archive_orphan_duplicate_scope_and_preservation(archival, mutation):
    root, old, _, mapping, _, _ = archival
    target = root / ce.MAPPING_PATH
    if mutation == 'missing-map':
        target.unlink()
    elif mutation == 'duplicate':
        mapping['entries'].append(mapping['entries'][0])
        target.write_text(json.dumps(mapping))
    elif mutation == 'omitted':
        mapping['entries'].pop()
        target.write_text(json.dumps(mapping))
    elif mutation == 'foreign-map':
        (target.parent / 'copy.json').write_bytes(target.read_bytes())
    elif mutation == 'extra-envelope':
        (target.parent / 'copy.log').write_bytes((root / mapping['entries'][0]['original']['path']).read_bytes())
    elif mutation == 'deleted-original':
        (root / mapping['entries'][0]['original']['path']).unlink()
    else:
        (target.parent / 'ordinary.log').write_bytes(b'new')
    head = commit(root)
    assert ce.archive_audit(root, head)[0]
    assert ce.audit(root, old, head, 'KL-080')['errors']


@pytest.mark.parametrize('mutation', ['missing', 'symlink', 'directory', 'tampered'])
def test_archive_payload_is_exact_revision_regular_blob(archival, mutation):
    root, _, _, mapping, original, _ = archival
    payload = root / mapping['entries'][0]['storage']['payload']
    saved = payload.read_bytes()
    payload.unlink()
    if mutation == 'symlink':
        payload.symlink_to(root / 'source')
    elif mutation == 'directory':
        payload.mkdir()
        (payload / 'child').write_bytes(b'bad')
    elif mutation == 'tampered':
        payload.write_bytes(b'corrupt')
    bad = commit(root)
    with pytest.raises(ValueError):
        ce.read_archive(root, mapping['entries'][0]['original']['path'], bad)
    if mutation == 'missing':
        payload.write_bytes(saved)
        later = commit(root)
        assert ce.read_archive(root, mapping['entries'][0]['original']['path'], later)
        with pytest.raises(ValueError):
            ce.read_archive(root, mapping['entries'][0]['original']['path'], bad)
    assert ce.read_archive(root, mapping['entries'][0]['original']['path'], original)


@pytest.mark.parametrize('encoding', ['utf-8', 'utf-16', 'utf-32'])
@pytest.mark.parametrize('wrapper', ['direct', 'list', 'dict', 'removed-marker', 'truncated'])
def test_archive_objects_never_become_execution_evidence(archival, encoding, wrapper):
    root, _, _, mapping, _, _ = archival
    value: object = dict(mapping)
    if wrapper == 'list':
        value = [mapping]
    elif wrapper == 'dict':
        value = {'wrapped': mapping}
    elif wrapper == 'removed-marker':
        assert isinstance(value, dict)
        value.pop(ce.MARKER)
    data = json.dumps(value).encode(encoding)
    if wrapper == 'truncated':
        data = data[:-3]
    ref = str(Path(ce.MAPPING_PATH).with_name('renamed.log'))
    (root / ref).write_bytes(data)
    head = commit(root)
    assert not v.evidence_exists(root, ref, head)
    outer = str(Path(ref).with_name('outer.json'))
    unchecked_storage(root, outer, data, head)
    nested = commit(root)
    assert not v.evidence_exists(root, outer, nested)
    assert ce.audit(root, head, nested, 'KL-080')['errors']


def test_archive_missing_original_has_no_head_or_archive_fallback(archival, monkeypatch):
    root, old, _, mapping, head, raws = archival
    original_git = ce.git
    def unavailable(root, *args):
        if old + '^{commit}' in args:
            raise ValueError('evidence-git:unavailable-original')
        return original_git(root, *args)
    monkeypatch.setattr(ce, 'git', unavailable)
    path = mapping['entries'][0]['original']['path']
    assert ce.read_archive(root, path, head) == raws[0]
    with pytest.raises(ValueError, match='unavailable-original'):
        ce.archive_original(root, mapping['entries'][0]['original'])
    with pytest.raises(ValueError, match='unavailable-original'):
        ce.read(root, path, old)
    assert ce.archive_audit(root, head)[0]


def test_archive_plain_and_aggregate_bounds_unchanged(archival, monkeypatch):
    root, old, _, mapping, head, _ = archival
    assert (ce.PLAIN_LIMIT, ce.STORED_LIMIT, ce.RAW_LIMIT, ce.TOTAL_LIMIT) == (
        256 * 1024, 8 * 1024 * 1024, 64 * 1024 * 1024, 16 * 1024 * 1024)
    total = ce.audit(root, old, head, 'KL-080')['stored_bytes']
    monkeypatch.setattr(ce, 'TOTAL_LIMIT', total - 1)
    assert any('PR-evidence-total' in e for e in ce.audit(root, old, head, 'KL-080')['errors'])
    monkeypatch.setattr(ce, 'RAW_LIMIT', 1)
    with pytest.raises(ValueError):
        ce.read_archive(root, mapping['entries'][0]['original']['path'], head)


@pytest.mark.parametrize('mutation', ['concatenated', 'trailing', 'truncated', 'corrupt', 'stored-bound'])
def test_archive_single_member_gzip_and_stored_bound(archival, mutation):
    root, _, _, mapping, _, _ = archival
    path = mapping['entries'][0]['original']['path']
    manifest = json.loads((root / path).read_bytes())
    target = root / manifest['payload']
    data = target.read_bytes()
    if mutation == 'concatenated':
        data += gzip.compress(b'borrowed', mtime=0)
    elif mutation == 'trailing':
        data += b'trailing'
    elif mutation == 'truncated':
        data = data[:-4]
    elif mutation == 'stored-bound':
        data = b'x' * (ce.STORED_LIMIT + 1)
    else:
        data = b'corrupt'
    target.write_bytes(data)
    manifest.update(stored_sha256=ce.digest(data), stored_bytes=len(data))
    (root / path).write_text(json.dumps(manifest))
    corrupt_storage = commit(root)
    with pytest.raises(ValueError):
        ce.archive_mapping(root, corrupt_storage)


def test_archive_mapping_cannot_rebind_forward_addition(archival):
    root, _, _, mapping, head, _ = archival
    (root / ce.MAPPING_PATH).write_text(json.dumps(mapping, indent=2))
    later = commit(root)
    errors = ce.audit(root, head, later, 'KL-080')['errors']
    assert any('archive-mapping-not-forward-addition' in e for e in errors)


@pytest.mark.parametrize('section,field,value', [
    ('execution_record', 'sha256', '0' * 64), ('execution_record', 'bytes', 1),
    ('execution_record', 'revision', '0' * 40),
])
def test_archive_original_metadata_record_cannot_be_rebound(archival, section, field, value):
    import copy
    root, _, _, mapping, head, _ = archival
    mapping = copy.deepcopy(mapping)
    mapping['entries'][0]['original'][section][field] = value
    with pytest.raises(ValueError):
        ce.validate_archive(root, mapping, head, verify_originals=True)


def test_archive_history_rewrite_cannot_supply_original_verification(archival):
    import copy
    root, _, storage, mapping, _, raws = archival
    unrelated = git(root, 'commit-tree', storage + '^{tree}', '-m', 'unrelated storage tree')
    mapping = copy.deepcopy(mapping)
    for entry in mapping['entries']:
        entry['storage']['revision'] = unrelated
    # Archive bytes may be recovered without original proof, but the gate must
    # reject the missing original-to-storage ancestry even with available blobs.
    assert list(ce.validate_archive(root, mapping, unrelated).values()) == raws
    with pytest.raises(ValueError):
        ce.validate_archive(root, mapping, unrelated, verify_originals=True)


@pytest.mark.parametrize('mutation', ['all-deleted', 'plain-truncation'])
def test_archive_complete_deletion_or_plain_substitution_cannot_evade_audit(archival, mutation):
    root, old, _, mapping, head, _ = archival
    for entry in mapping['entries']:
        path = root / entry['original']['path']
        path.unlink()
        (root / entry['storage']['payload']).unlink()
        if mutation == 'plain-truncation':
            path.write_bytes(b'1 passed in 0.1s\n')
    (root / ce.MAPPING_PATH).unlink()
    later = commit(root)
    assert ce.audit(root, old, later, 'KL-080')['errors']
    assert ce.audit(root, head, later, 'HG-999')['errors']


@pytest.fixture
def installed_archive_decoder(tmp_path):
    # Match the worker's layout, with no schema next to its pinned Python assets.
    installed = tmp_path / 'gate/tools/harness'
    installed.mkdir(parents=True)
    for name in ('compact_evidence.py', 'validate_harness.py'):
        (installed / name).write_bytes((ROOT / 'tools/harness' / name).read_bytes())
    spec = importlib.util.spec_from_file_location('installed_validator', installed / 'validate_harness.py')
    assert spec and spec.loader
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    return validator


def test_archive_installed_decoder_has_pinned_authority(installed_archive_decoder, tmp_path, monkeypatch):
    installed = installed_archive_decoder.compact_evidence
    assert installed.historical_schema() == ce.historical_schema()
    assert installed.HISTORICAL_SCHEMA_BYTES == (ROOT / ce.MAPPING_SCHEMA).read_bytes()
    # Neither an ambient /gate schema nor a candidate working-directory schema
    # can widen the decoder inventory, even with valid but different JSON.
    (tmp_path / 'gate' / ce.MAPPING_SCHEMA).write_text('{}')
    monkeypatch.chdir(tmp_path)
    (tmp_path / ce.MAPPING_SCHEMA).write_text('{}')
    assert installed.historical_originals() == ce.historical_originals()
    assert installed.historical_template() == ce.historical_template()


@pytest.mark.parametrize('mutation', ['missing', 'tampered', 'symlink', 'oversize'])
def test_archive_installed_validator_rejects_candidate_schema(installed_archive_decoder, tmp_path, mutation):
    candidate = tmp_path / 'candidate'
    candidate.mkdir()
    schema = candidate / ce.MAPPING_SCHEMA
    if mutation == 'tampered':
        value = ce.historical_schema()
        value['properties']['entries']['prefixItems'][0]['properties']['original']['const']['raw_sha256'] = '0' * 64
        schema.write_text(json.dumps(value))
    elif mutation == 'symlink':
        schema.symlink_to(ROOT / ce.MAPPING_SCHEMA)
    elif mutation == 'oversize':
        schema.write_bytes(b' ' * (ce.PLAIN_LIMIT + 1))
    # Early fail-closed rejection precedes any candidate index/manifest reads.
    errors = installed_archive_decoder.validate(candidate, None)
    assert errors and all(error.startswith('historical-schema-authority:') for error in errors)
    assert installed_archive_decoder.compact_evidence.historical_originals() == ce.historical_originals()


def test_archive_installed_validator_accepts_exact_schema(installed_archive_decoder, tmp_path):
    candidate = tmp_path / 'candidate'
    candidate.mkdir()
    (candidate / ce.MAPPING_SCHEMA).write_bytes((ROOT / ce.MAPPING_SCHEMA).read_bytes())
    assert installed_archive_decoder.historical_schema_authority_errors(candidate) == []
