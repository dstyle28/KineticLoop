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


@pytest.mark.parametrize('codec', [ce.FORMAT, ce.XZ_FORMAT])
def test_both_codecs_exact_bound_readers(repo, codec):
    root, base = repo
    raw = b'\xff\x00' + bytes(range(256)) * 100 + b'2 passed\n1 failed\n'
    record = ce.capture(root, REF, raw, base, 'pytest', 1, None, codec)
    head = commit(root)
    assert ce.encode(raw, codec) == ce.encode(raw, codec)
    assert (root / record['payload']).read_bytes() == ce.encode(raw, codec)
    assert ce.read(root, REF, head, tested=base, command='pytest', exit_code=1) == raw
    assert not v.evidence_exists(root, REF, head, base, 'pytest', 0)
    assert v.evidence_exists(root, REF, head, base, 'pytest', 1)
    assert v.m3_evidence_bytes(root, {'path': REF, 'revision': head,
                                    'sha256': ce.digest((root / REF).read_bytes())}, head) == raw
    assert ce.audit(root, base, head, 'HG-047')['errors'] == []
    assert record['test_counts'] == {'passed': 2, 'failed': 1}


@pytest.mark.parametrize('mutation', ['truncated', 'trailing', 'concatenated', 'corrupt',
                                      'no-check', 'crc32', 'sha256', 'dict-bomb', 'raw-bomb',
                                      'wrong-codec', 'stored-hash', 'raw-hash'])
def test_xz_hostile_streams(repo, mutation):
    import lzma
    root, base = repo
    record = ce.capture(root, REF, b'a', base, 'pytest', 0, codec=ce.XZ_FORMAT)
    stored = (root / record['payload']).read_bytes()
    if mutation == 'truncated':
        stored = stored[:-4]
    elif mutation == 'trailing':
        stored += b'junk'
    elif mutation == 'concatenated':
        stored += stored
    elif mutation == 'corrupt':
        stored = stored[:30] + bytes([stored[30] ^ 255]) + stored[31:]
    elif mutation in ('no-check', 'crc32', 'sha256'):
        stored = lzma.compress(b'a', check={'no-check': lzma.CHECK_NONE,
                                          'crc32': lzma.CHECK_CRC32,
                                          'sha256': lzma.CHECK_SHA256}[mutation])
    elif mutation == 'dict-bomb':
        stored = lzma.compress(b'a', filters=[{'id': lzma.FILTER_LZMA2, 'dict_size': 128 << 20}])
    elif mutation == 'raw-bomb':
        stored = ce.encode(b'a' * 1000000, ce.XZ_FORMAT)
    elif mutation == 'wrong-codec':
        stored = ce.encode(b'a', ce.FORMAT)
    record.update(stored_bytes=len(stored), stored_sha256=ce.digest(stored))
    (root / record['payload']).write_bytes(stored)
    if mutation == 'stored-hash':
        record['stored_sha256'] = '0' * 64
    if mutation == 'raw-hash':
        record['raw_sha256'] = '0' * 64
    head = replace_record(root, record)
    with pytest.raises(ValueError):
        ce.read(root, REF, head)
    assert ce.audit(root, base, head, 'HG-047')['errors']


@pytest.mark.parametrize('encoding', ENCODINGS)
@pytest.mark.parametrize('wrapper', [False, True])
def test_xz_reserved_encoded_nested_output_rejected(repo, encoding, wrapper):
    root, base = repo
    value = {ce.MARKER: 'xz-v1'}
    raw = json.dumps([value] if wrapper else value).encode(encoding)
    with pytest.raises(ValueError):
        ce.capture(root, REF, raw, base, 'pytest', 0, codec=ce.XZ_FORMAT)
    assert not (root / REF).exists()


RECODE = 'docs/exec-plans/evidence/HG-047/conversion/COMPACT_REENCODING.json'


def converted(repo, refs=None):
    root, base = repo
    refs = refs or [REF]
    raw = bytes(range(256)) * 100 + b'1 failed\n'
    for ref in refs:
        ce.capture(root, ref, raw, base, 'pytest -q', 1, '2026-10-04T00:00:00Z')
    source = commit(root)
    record = ce.reencode(root, base, source, 'HG-047', refs, RECODE, ce.XZ_FORMAT)
    head = commit(root)
    return root, base, source, record, head, raw


def test_forward_own_conversion_preserves_original_and_failure(repo):
    root, base, source, record, head, raw = converted(repo)
    assert ce.read(root, REF, source, exit_code=1) == raw
    assert ce.read(root, REF, head, exit_code=1) == raw
    assert not v.evidence_exists(root, REF, head, base, 'pytest -q', 0)
    assert ce.audit(root, base, head, 'HG-047')['errors'] == []
    assert not (root / record['entries'][0]['original']['payload']['path']).exists()
    assert record['entries'][0]['execution']['test_counts'] == {'failed': 1}
    with pytest.raises(ValueError):
        ce.read(root, RECODE, head)


@pytest.mark.parametrize('mutation', ['foreign', 'protected', 'plain', 'archive', 'missing-source',
                                      'nonancestor', 'working-tamper', 'alias-source', 'same-codec'])
def test_forward_conversion_rejects_ineligible_inputs_without_changes(repo, mutation):
    root, base, before, source = captured(repo)
    selected_base, selected_source, identity, codec = base, source, 'HG-047', ce.XZ_FORMAT
    if mutation == 'foreign':
        identity = 'HG-054'
    elif mutation == 'protected':
        selected_base = source
    elif mutation == 'plain':
        (root / REF).write_text('1 passed\n')
        selected_source = commit(root)
    elif mutation == 'archive':
        before[ce.MARKER] = ce.HISTORICAL_FORMAT
        selected_source = replace_record(root, before)
    elif mutation == 'missing-source':
        selected_source = '0' * 40
    elif mutation == 'alias-source':
        selected_source = 'HEAD'
    elif mutation == 'nonancestor':
        git(root, 'checkout', '--orphan', 'other')
        (root / 'source').write_text('other')
        commit(root)
    elif mutation == 'working-tamper':
        (root / REF).write_text('tamper')
    elif mutation == 'same-codec':
        codec = ce.FORMAT
    old = {str(p.relative_to(root)): p.read_bytes() for p in (root / 'docs').rglob('*') if p.is_file()}
    with pytest.raises(ValueError):
        ce.reencode(root, selected_base, selected_source, identity, [REF], RECODE, codec)
    new = {str(p.relative_to(root)): p.read_bytes() for p in (root / 'docs').rglob('*') if p.is_file()}
    assert new == old


@pytest.mark.parametrize('mutation', ['command', 'tested_commit', 'exit_code', 'timestamp', 'test_counts',
                                      'source', 'original-hash', 'original-blob', 'new-hash',
                                      'map-delete', 'map-rename', 'envelope-delete', 'payload-delete',
                                      'map-wrapped'])
def test_forward_mapping_tamper_rejected(repo, mutation):
    root, base, source, record, head, _ = converted(repo)
    if mutation in ce.EXECUTION_FIELDS:
        entry = json.loads((root / REF).read_text())
        entry[mutation] = {'passed': 1} if mutation == 'test_counts' else 0
        (root / REF).write_text(json.dumps(entry))
    elif mutation == 'source':
        record['source_revision'] = '0' * 40
    elif mutation == 'original-hash':
        record['entries'][0]['original']['envelope']['sha256'] = '0' * 64
    elif mutation == 'original-blob':
        record['entries'][0]['original']['payload']['blob_id'] = '0' * 40
    elif mutation == 'new-hash':
        record['entries'][0]['replacement']['payload']['sha256'] = '0' * 64
    elif mutation == 'map-delete':
        (root / RECODE).unlink()
    elif mutation == 'map-rename':
        (root / RECODE).rename((root / RECODE).with_name('renamed.json'))
    elif mutation == 'envelope-delete':
        (root / REF).unlink()
    elif mutation == 'payload-delete':
        (root / record['entries'][0]['replacement']['payload']['path']).unlink()
    if mutation not in ('map-delete', 'map-rename'):
        (root / RECODE).write_text(json.dumps([record] if mutation == 'map-wrapped' else record))
    head = commit(root)
    assert ce.audit(root, base, head, 'HG-047')['errors']
    assert ce.read(root, REF, source) == bytes(range(256)) * 100 + b'1 failed\n'


def test_unmapped_conversion_and_reverted_deletion_rejected(repo):
    root, base, before, source = captured(repo)
    raw = ce.read(root, REF, source)
    (root / REF).unlink()
    (root / before['payload']).unlink()
    ce.capture(root, REF, raw, base, 'pytest', 0, codec=ce.XZ_FORMAT)
    head = commit(root)
    assert ce.audit(root, base, head, 'HG-047')['errors']
    git(root, 'checkout', source, '--', REF, before['payload'])
    head = commit(root)
    assert ce.audit(root, base, head, 'HG-047')['errors']


def test_shared_payload_removed_only_after_all_current_refs_converted(repo):
    root, base = repo
    second = REF.replace('run.json', 'second.json')
    for ref in [REF, second]:
        ce.capture(root, ref, b'1 failed\n', base, 'pytest', 1)
    source = commit(root)
    record = ce.reencode(root, base, source, 'HG-047', [REF], RECODE, ce.XZ_FORMAT)
    old = record['entries'][0]['original']['payload']['path']
    assert (root / old).exists()
    head = commit(root)
    assert ce.read(root, second, head) == b'1 failed\n'
    assert ce.audit(root, base, head, 'HG-047')['errors'] == []


def test_all_shared_refs_conversion_and_changed_byte_accounting(repo):
    second = REF.replace('run.json', 'second.json')
    root, base, _, record, head, _ = converted(repo, [REF, second])
    old = record['entries'][0]['original']['payload']['path']
    assert not (root / old).exists()
    assert record['entries'][0]['replacement']['payload'] == record['entries'][1]['replacement']['payload']
    report = ce.audit(root, base, head, 'HG-047')
    assert report['errors'] == []
    files = [p for p in (root / 'docs').rglob('*') if p.is_file()]
    assert report['stored_bytes'] == sum(p.stat().st_size for p in files)


def test_codec_limits_unchanged_and_inclusive(repo, monkeypatch):
    assert (ce.PLAIN_LIMIT, ce.STORED_LIMIT, ce.RAW_LIMIT, ce.TOTAL_LIMIT) == (
        256 * 1024, 8 * 1024 * 1024, 64 * 1024 * 1024, 16 * 1024 * 1024)
    root, base = repo
    raw = b'a' * 1000
    stored = ce.encode(raw, ce.XZ_FORMAT)
    monkeypatch.setattr(ce, 'RAW_LIMIT', len(raw))
    monkeypatch.setattr(ce, 'STORED_LIMIT', len(stored))
    ce.capture(root, REF, raw, base, 'pytest', 0, codec=ce.XZ_FORMAT)
    head = commit(root)
    assert ce.read(root, REF, head) == raw
    monkeypatch.setattr(ce, 'RAW_LIMIT', len(raw) - 1)
    with pytest.raises(ValueError):
        ce.read(root, REF, head)


def test_xz_orphan_and_two_codec_bulk_copies_are_accounted(repo):
    root, base = repo
    raw = bytes(range(256)) * 100
    first = ce.capture(root, REF, raw, base, 'pytest', 0, codec=ce.XZ_FORMAT)
    second = ce.capture(root, REF.replace('run.json', 'other.json'), raw, base, 'pytest', 0)
    head = commit(root)
    report = ce.audit(root, base, head, 'HG-047')
    assert any('duplicate-bulk' in error for error in report['errors'])
    assert report['stored_bytes'] >= first['stored_bytes'] + second['stored_bytes']
    (root / first['payload']).with_name('orphan.xz').write_bytes(b'orphan')
    head = commit(root)
    assert any('orphan.xz:unreferenced-payload' in e for e in ce.audit(root, base, head, 'HG-047')['errors'])


def test_second_conversion_and_shared_live_payload_deletion_fail(repo):
    root, base, _, _, head, _ = converted(repo)
    before = (root / REF).read_bytes()
    with pytest.raises(ValueError, match='already-mapped'):
        ce.reencode(root, base, head, 'HG-047', [REF],
                    RECODE.replace('/conversion/', '/second/'), ce.FORMAT)
    assert (root / REF).read_bytes() == before


def test_mapping_original_source_loss_is_fail_closed(repo, monkeypatch):
    root, base, source, record, head, _ = converted(repo)
    original = ce.blob
    def missing(root_arg, path, revision, limit=None):
        if revision == source:
            raise ValueError('source unavailable')
        return original(root_arg, path, revision, limit)
    monkeypatch.setattr(ce, 'blob', missing)
    with pytest.raises(ValueError, match='source unavailable'):
        ce.validate_reencoding(root, RECODE, record, base, head, 'HG-047')


def test_all_selection_validated_before_first_mutation(repo):
    root, base, record, source = captured(repo)
    other = REF.replace('run.json', 'plain.log')
    (root / other).write_text('plain historical bytes')
    source = commit(root)
    before = (root / REF).read_bytes()
    stored = (root / record['payload']).read_bytes()
    with pytest.raises(ValueError):
        ce.reencode(root, base, source, 'HG-047', [REF, other], RECODE, ce.XZ_FORMAT)
    assert (root / REF).read_bytes() == before
    assert (root / record['payload']).read_bytes() == stored
    assert not (root / RECODE).exists()


@pytest.mark.parametrize('mutation', ['codec', 'metadata', 'raw'])
def test_retained_old_alias_cannot_excuse_unmapped_original_path_change(repo, mutation):
    root, base, before, source = captured(repo)
    alias = REF.replace('run.json', 'kept-original.json')
    (root / alias).write_bytes((root / REF).read_bytes())
    (root / REF).unlink()
    raw = ce.read(root, REF, source)
    if mutation == 'raw':
        raw = b'different 1 passed\n'
    ce.capture(root, REF, raw, base, 'other' if mutation == 'metadata' else 'pytest', 0,
               before['timestamp'], ce.XZ_FORMAT if mutation == 'codec' else ce.FORMAT)
    head = commit(root)
    assert ce.read(root, REF, head) == raw
    assert ce.read(root, alias, head) == ce.read(root, REF, source)
    assert any('unmapped-envelope-mutation' in error for error in
               ce.audit(root, base, head, 'HG-047')['errors'])


def test_handcrafted_older_base_cannot_admit_previously_merged_compact_source(repo):
    root, original_base, before, source = captured(repo)
    (root / REF).unlink()
    (root / before['payload']).unlink()
    protected_base = commit(root)  # Source was already in protected history, then deleted.
    # Wrong claimed base permits local tool staging, but the actual PR-base audit
    # must reject this historical source even though both paths are now absent.
    git(root, 'checkout', source, '--', REF, before['payload'])
    commit(root)  # Satisfy HEAD-snapshot guard; actual protected source is still older.
    record = ce.reencode(root, original_base, source, 'HG-047', [REF], RECODE, ce.XZ_FORMAT)
    head = commit(root)
    with pytest.raises(ValueError):
        ce.validate_reencoding(root, RECODE, record, protected_base, head, 'HG-047')
    assert ce.audit(root, protected_base, head, 'HG-047')['errors']


def test_conversion_write_failure_restores_all_original_bytes(repo, monkeypatch):
    root, base, before, source = captured(repo)
    data = (root / REF).read_bytes()
    stored = (root / before['payload']).read_bytes()
    validate = ce.validate_reencoding
    def fail(*args, **kwargs):
        raise ValueError('simulated validation failure')
    monkeypatch.setattr(ce, 'validate_reencoding', fail)
    with pytest.raises(ValueError, match='simulated'):
        ce.reencode(root, base, source, 'HG-047', [REF], RECODE, ce.XZ_FORMAT)
    monkeypatch.setattr(ce, 'validate_reencoding', validate)
    assert (root / REF).read_bytes() == data
    assert (root / before['payload']).read_bytes() == stored
    assert not list((root / REF).parent.glob('*.xz'))
    assert not (root / RECODE).exists()


@pytest.mark.parametrize('encoding', ENCODINGS)
@pytest.mark.parametrize('wrapper', [False, True])
def test_mapping_removed_marker_never_becomes_execution_output(repo, encoding, wrapper):
    root, base, source, record, head, _ = converted(repo)
    del record[ce.REENCODING_KEY]
    (root / RECODE).write_bytes(json.dumps([record] if wrapper else record).encode(encoding))
    head = commit(root)
    with pytest.raises(ValueError):
        ce.read(root, RECODE, head)
    assert ce.audit(root, base, head, 'HG-047')['errors']
    assert ce.read(root, REF, source) == bytes(range(256)) * 100 + b'1 failed\n'


def test_merged_mapping_stays_immutable_and_reverifies_originals(repo, monkeypatch):
    root, _, source, record, base, _ = converted(repo)
    report = ce.audit(root, base, base, 'HG-047')
    assert report['errors'] == [] and report['stored_bytes'] == 0
    original = ce.blob
    def missing(root_arg, path, revision, limit=None):
        if revision == source:
            raise ValueError('source unavailable')
        return original(root_arg, path, revision, limit)
    monkeypatch.setattr(ce, 'blob', missing)
    assert ce.audit(root, base, base, 'HG-047')['errors']
    monkeypatch.setattr(ce, 'blob', original)
    (root / RECODE).unlink()
    head = commit(root)
    assert ce.audit(root, base, head, 'HG-047')['errors']


def test_unrelated_owner_audit_reverifies_every_admitted_original_blob(repo):
    root, _, source, record, base, raw = converted(repo)
    assert ce.audit(root, base, base, 'HG-048')['errors'] == []
    original = record['entries'][0]['original']['payload']
    oid = git(root, 'rev-parse', source + ':' + original['path'])
    # Only this newly initialized fixture's loose object; never real repo objects.
    target = root / '.git/objects' / oid[:2] / oid[2:]
    assert target.is_file() and root.resolve() in target.resolve().parents
    target.unlink()
    assert ce.read(root, REF, base) == raw
    assert any('reencoding-invalid' in error for error in ce.audit(root, base, base, 'HG-048')['errors'])


@pytest.mark.parametrize('mutation', ['delete', 'change'])
def test_unrelated_owner_audit_enforces_admitted_map_immutability(repo, mutation):
    root, _, _, record, base, _ = converted(repo)
    if mutation == 'delete':
        (root / RECODE).unlink()
    else:
        record['identity'] = 'HG-048'
        (root / RECODE).write_text(json.dumps(record))
    head = commit(root)
    assert ce.audit(root, base, head, 'HG-048')['errors']


@pytest.mark.parametrize('artifact', ['mapping', 'envelope', 'payload'])
@pytest.mark.parametrize('mutation', ['delete', 'change'])
def test_unrelated_owner_rejects_transient_admitted_binding_mutation(repo, artifact, mutation):
    root, _, _, record, base, _ = converted(repo)
    replacement = record['entries'][0]['replacement']
    path = RECODE if artifact == 'mapping' else replacement[artifact]['path']
    original = (root / path).read_bytes()
    if mutation == 'delete':
        (root / path).unlink()
    else:
        (root / path).write_bytes(original + b'changed')
    commit(root)
    (root / path).write_bytes(original)
    head = commit(root)
    assert ce.read(root, REF, head) == ce.read(root, REF, base)
    assert ce.audit(root, base, head, 'HG-048')['errors']


def test_unrelated_owner_rejects_restored_mapping_on_merged_post_admission_branch(repo):
    root, _, _, _, base, _ = converted(repo)
    main = git(root, 'branch', '--show-current')
    original = (root / RECODE).read_bytes()
    git(root, 'checkout', '-qb', 'after-admission', base)
    (root / RECODE).unlink()
    commit(root)
    (root / RECODE).write_bytes(original)
    commit(root)
    git(root, 'checkout', main)
    git(root, 'merge', '--no-ff', '-qm', 'fixture merge', 'after-admission')
    head = git(root, 'rev-parse', 'HEAD')
    assert ce.audit(root, base, head, 'HG-048')['errors']


def test_pre_admission_side_branch_needs_no_retroactive_inherited_mapping(repo):
    root, _, source, _, base, _ = converted(repo)
    main = git(root, 'branch', '--show-current')
    git(root, 'checkout', '-qb', 'before-admission', source)
    (root / 'unrelated').write_text('ordinary side branch before map admission')
    commit(root)
    git(root, 'checkout', main)
    git(root, 'merge', '--no-ff', '-qm', 'fixture merge', 'before-admission')
    head = git(root, 'rev-parse', 'HEAD')
    assert ce.audit(root, base, head, 'HG-048')['errors'] == []


@pytest.mark.parametrize('mapping', [True, False])
def test_transient_foreign_conversion_cannot_disappear_before_head(repo, mapping):
    root, base, before, source = captured(repo)
    if mapping:
        ce.reencode(root, base, source, 'HG-047', [REF], RECODE, ce.XZ_FORMAT)
    else:
        raw = ce.read(root, REF, source)
        (root / REF).unlink()
        ce.capture(root, REF, raw, base, 'pytest', 0, before['timestamp'], ce.XZ_FORMAT)
    commit(root)
    for path in list((root / REF).parent.rglob('*')):
        if path.is_file():
            path.unlink()
    head = commit(root)
    assert git(root, 'diff', '--name-only', base, head) == ''
    assert ce.audit(root, base, head, 'HG-054')['errors']


@pytest.mark.parametrize('artifact', ['envelope', 'payload'])
def test_unmapped_foreign_compact_mutation_and_restoration_fails(repo, artifact):
    root, _, before, base = captured(repo)
    path = REF if artifact == 'envelope' else before['payload']
    original = (root / path).read_bytes()
    (root / path).write_bytes(original + b'changed')
    commit(root)
    (root / path).write_bytes(original)
    head = commit(root)
    assert ce.audit(root, base, head, 'HG-054')['errors']


@pytest.mark.parametrize('name', ['COMPACT_REENCODING.json', 'renamed.json', 'renamed.gz', 'renamed.xz'])
@pytest.mark.parametrize('encoding', ['utf-8', 'utf-16', 'utf-32'])
@pytest.mark.parametrize('shape', ['wrapped', 'nested', 'removed-marker'])
def test_transient_reserved_new_map_on_pre_admission_branch_fails_globally(repo, name, encoding, shape):
    root, original_base = repo
    main = git(root, 'branch', '--show-current')
    (root / 'later-protected-source').write_text('ordinary protected update')
    base = commit(root)
    git(root, 'checkout', '-qb', 'old-side-branch', original_base)
    target = root / str(Path(RECODE).with_name(name))
    target.parent.mkdir(parents=True)
    value = ([{ce.REENCODING_KEY: 'v1'}] if shape == 'wrapped' else
             {'nested': {ce.REENCODING_KEY: 'v1'}} if shape == 'nested' else
             {'protected_base': original_base, 'source_revision': original_base, 'entries': []})
    target.write_bytes(json.dumps(value).encode(encoding))
    commit(root)
    target.unlink()
    commit(root)
    git(root, 'checkout', main)
    git(root, 'merge', '--no-ff', '-qm', 'fixture merge', 'old-side-branch')
    head = git(root, 'rev-parse', 'HEAD')
    assert git(root, 'diff', '--name-only', base, head) == ''
    assert ce.audit(root, base, head, 'HG-054')['errors']


def test_mapping_marker_name_in_plain_prose_stays_ordinary_output(repo):
    root, base = repo
    path = REF.replace('run.json', 'note.log')
    target = root / path
    target.parent.mkdir(parents=True)
    data = b'Prose mentions compact_reencoding without a storage object.\n'
    target.write_bytes(data)
    head = commit(root)
    assert ce.read(root, path, head) == data
    assert ce.audit(root, base, head, 'HG-047')['errors'] == []


@pytest.mark.parametrize('name', ['renamed.json', 'renamed.gz', 'renamed.xz'])
@pytest.mark.parametrize('encoding', ['utf-8', 'utf-16', 'utf-32'])
@pytest.mark.parametrize('shape', ['partial-envelope', 'removed-marker', 'fake-archive'])
def test_transient_invalid_execution_storage_on_pre_admission_branch_fails(repo, name, encoding, shape):
    root, original_base = repo
    main = git(root, 'branch', '--show-current')
    (root / 'later-protected-source').write_text('ordinary protected update')
    base = commit(root)
    git(root, 'checkout', '-qb', 'old-side-branch', original_base)
    target = root / str(Path(RECODE).with_name(name))
    target.parent.mkdir(parents=True)
    value = ({ce.MARKER: ce.XZ_FORMAT} if shape == 'partial-envelope' else
             {'payload': 'missing', 'stored_sha256': 'missing', 'raw_sha256': 'missing'}
             if shape == 'removed-marker' else {ce.MARKER: ce.HISTORICAL_FORMAT})
    target.write_bytes(json.dumps(value).encode(encoding))
    introduced = commit(root)
    with pytest.raises(ValueError):
        ce.read(root, str(target.relative_to(root)), introduced)
    target.unlink()
    commit(root)
    git(root, 'checkout', main)
    git(root, 'merge', '--no-ff', '-qm', 'fixture merge', 'old-side-branch')
    head = git(root, 'rev-parse', 'HEAD')
    assert git(root, 'diff', '--name-only', base, head) == ''
    assert ce.audit(root, base, head, 'HG-054')['errors']


@pytest.mark.parametrize('codec', ce.CODECS)
def test_valid_pre_admission_compact_execution_stays_bound_to_original_bytes(repo, codec):
    root, original_base = repo
    main = git(root, 'branch', '--show-current')
    (root / 'later-protected-source').write_text('ordinary protected update')
    base = commit(root)
    git(root, 'checkout', '-qb', 'old-side-branch', original_base)
    before = ce.capture(root, REF, b'1 failed\n', original_base, 'pytest', 1, codec=codec)
    source = commit(root)
    for path in (REF, before['payload']):
        (root / path).unlink()
    commit(root)
    git(root, 'checkout', main)
    git(root, 'merge', '--no-ff', '-qm', 'fixture merge', 'old-side-branch')
    head = git(root, 'rev-parse', 'HEAD')
    assert ce.read(root, REF, source) == b'1 failed\n'
    assert ce.audit(root, base, head, 'HG-054')['errors'] == []


@pytest.mark.parametrize('codec', ce.CODECS)
@pytest.mark.parametrize('marker_value', [ce.MARKER, ce.REENCODING_KEY])
def test_bound_binary_payload_marker_value_stays_ordinary_output(repo, codec, marker_value):
    root, base = repo
    raw = json.dumps({'ordinary': marker_value}, separators=(',', ':')).encode()
    assert ce.envelope(raw) is None
    before = ce.capture(root, REF, raw, base, 'pytest', 1, codec=codec)
    head = commit(root)
    assert ce.read(root, REF, head, tested=base, command='pytest', exit_code=1) == raw
    assert ce.audit(root, base, head, 'HG-047')['errors'] == []
    assert before['exit_code'] == 1


@pytest.mark.parametrize('codec', ce.CODECS)
@pytest.mark.parametrize('field', ['stored_sha256', 'raw_sha256', 'stored_bytes', 'raw_bytes', 'tested_commit'])
def test_binary_marker_payload_exemption_requires_full_bound_proof(repo, codec, field):
    root, base = repo
    raw = b'{"ordinary":"kineticloop_evidence"}'
    before = ce.capture(root, REF, raw, base, 'pytest', 1, codec=codec)
    before[field] = '0' * (40 if field == 'tested_commit' else 64) if 'sha256' in field or field == 'tested_commit' else 1
    head = replace_record(root, before)
    with pytest.raises(ValueError):
        ce.read(root, REF, head)
    assert ce.audit(root, base, head, 'HG-047')['errors']


@pytest.mark.parametrize('codec', ce.CODECS)
def test_binary_marker_payload_proof_cannot_use_later_revision(repo, codec):
    root, base = repo
    before = ce.capture(root, REF, b'{"ordinary":"kineticloop_evidence"}', base, 'pytest', 1, codec=codec)
    target = root / before['payload']
    stored = target.read_bytes()
    target.unlink()
    missing = commit(root)
    target.write_bytes(stored)
    head = commit(root)
    assert ce.read(root, REF, head) == b'{"ordinary":"kineticloop_evidence"}'
    with pytest.raises(ValueError):
        ce.read(root, REF, missing)
    assert ce.audit(root, base, head, 'HG-047')['errors']


@pytest.mark.parametrize('codec', ce.CODECS)
def test_binary_marker_payload_exemption_rejects_nested_storage(repo, codec):
    root, base = repo
    before = ce.capture(root, REF, b'{"ordinary":"kineticloop_evidence"}', base, 'pytest', 1, codec=codec)
    (root / before['payload']).unlink()
    raw = json.dumps({'nested': {ce.REENCODING_KEY: 'v1'}}).encode()
    stored = ce.encode(raw, codec)
    payload = str(Path(REF).parent / (ce.digest(raw) + ce.CODECS[codec]))
    before.update(payload=payload, raw_sha256=ce.digest(raw), raw_bytes=len(raw),
                  stored_sha256=ce.digest(stored), stored_bytes=len(stored))
    (root / payload).write_bytes(stored)
    head = replace_record(root, before)
    with pytest.raises(ValueError):
        ce.read(root, REF, head)
    assert ce.audit(root, base, head, 'HG-047')['errors']


@pytest.mark.parametrize('codec', ce.CODECS)
def test_binary_marker_payload_unchanged_envelope_pre_admission_restoration(repo, codec):
    root, original_base = repo
    main = git(root, 'branch', '--show-current')
    (root / 'later-protected-source').write_text('ordinary protected update')
    base = commit(root)
    git(root, 'checkout', '-qb', 'old-side-branch', original_base)
    raw = b'{"ordinary":"kineticloop_evidence"}'
    before = ce.capture(root, REF, raw, original_base, 'pytest', 1, codec=codec)
    source = commit(root)
    target = root / before['payload']
    stored = target.read_bytes()
    target.unlink()
    commit(root)
    target.write_bytes(stored)
    restored = commit(root)
    for path in (REF, before['payload']):
        (root / path).unlink()
    commit(root)
    git(root, 'checkout', main)
    git(root, 'merge', '--no-ff', '-qm', 'fixture merge', 'old-side-branch')
    head = git(root, 'rev-parse', 'HEAD')
    assert ce.read(root, REF, source, exit_code=1) == raw
    assert ce.read(root, REF, restored, exit_code=1) == raw
    assert ce.audit(root, base, head, 'HG-054')['errors'] == []


CONSOLIDATED = 'docs/exec-plans/evidence/HG-047/consolidated'


def relocated(repo):
    root, base = repo
    refs = [REF.replace('/run.json', '/first/run.json'), REF.replace('/run.json', '/second/run.json')]
    raw = bytes(range(256)) * 100 + b'1 failed\n'
    before = [ce.capture(root, ref, raw, base, 'pytest ' + str(i), i, None)
              for i, ref in enumerate(refs)]
    source = commit(root)
    assert any('duplicate-bulk' in error for error in ce.audit(root, base, source, 'HG-047')['errors'])
    record = ce.reencode(root, base, source, 'HG-047', refs, RECODE, ce.XZ_FORMAT, CONSOLIDATED)
    head = commit(root)
    return root, base, source, record, head, raw, refs, before


def test_explicit_relocation_shares_payload_preserving_distinct_executions(repo):
    root, base, source, record, head, raw, refs, before = relocated(repo)
    destinations = [entry['replacement']['envelope']['path'] for entry in record['entries']]
    assert len(set(destinations)) == 2
    assert record['entries'][0]['replacement']['payload'] == record['entries'][1]['replacement']['payload']
    for original, destination, manifest in zip(refs, destinations, before, strict=True):
        assert not (root / original).exists() and not (root / manifest['payload']).exists()
        assert ce.read(root, original, source) == ce.read(root, destination, head) == raw
        assert v.review_reference_available(root, original, source)
        assert not v.review_reference_available(root, original, '0' * 40)
        current = json.loads((root / destination).read_text())
        assert all(current[key] == manifest[key] for key in ce.EXECUTION_FIELDS)
        assert Path(current['payload']).parent == Path(destination).parent
    assert ce.audit(root, base, head, 'HG-047')['errors'] == []
    assert v.storage_bookkeeping_only(root, source, head, RECODE) is False
    # The next genuine execution can share only stored bytes, with its own metadata.
    new = CONSOLIDATED + '/new-execution.json'
    ce.capture(root, new, raw, head, 'pytest new', 0, codec=ce.XZ_FORMAT)
    final = commit(root)
    assert ce.read(root, new, final, tested=head, command='pytest new', exit_code=0) == raw
    assert ce.audit(root, base, final, 'HG-047')['errors'] == []


@pytest.mark.parametrize('selection', ['original', 'replacement'])
def test_relocated_immutable_map_cannot_be_superseded(repo, selection):
    root, base, _, record, head, _, _, _ = relocated(repo)
    ref = record['entries'][0][selection]['envelope']['path']
    with pytest.raises(ValueError, match='already-mapped'):
        ce.reencode(root, base, head, 'HG-047', [ref], RECODE.replace('/conversion/', '/again/'), ce.FORMAT)


@pytest.mark.parametrize('mutation', ['restore-original', 'delete-replacement', 'modify-replacement',
                                      'delete-payload', 'delete-map', 'move-foreign', 'source-unavailable'])
def test_relocated_mapping_guards_every_bound_object(repo, mutation):
    root, base, source, record, _, _, refs, _ = relocated(repo)
    replacement = record['entries'][0]['replacement']
    if mutation == 'restore-original':
        (root / refs[0]).write_bytes(ce.blob(root, refs[0], source))
    elif mutation == 'delete-replacement':
        (root / replacement['envelope']['path']).unlink()
    elif mutation == 'modify-replacement':
        p = root / replacement['envelope']['path']
        manifest = json.loads(p.read_text())
        manifest['command'] = 'different'
        p.write_text(json.dumps(manifest))
    elif mutation == 'delete-payload':
        (root / replacement['payload']['path']).unlink()
    elif mutation == 'delete-map':
        (root / RECODE).unlink()
    elif mutation == 'move-foreign':
        record['entries'][0]['replacement']['envelope']['path'] = replacement['envelope']['path'].replace('HG-047', 'HG-048')
        (root / RECODE).write_text(json.dumps(record))
    else:
        record['source_revision'] = '0' * 40
        (root / RECODE).write_text(json.dumps(record))
    bad = commit(root)
    assert ce.audit(root, base, bad, 'HG-047')['errors']
    if mutation == 'restore-original':
        (root / refs[0]).unlink()
        restored = commit(root)
        assert ce.audit(root, base, restored, 'HG-047')['errors']


@pytest.mark.parametrize('directory', ['docs/exec-plans/evidence/HG-048/shared',
                                       'docs/exec-plans/reviews/HG-047/shared',
                                       'docs/exec-plans/evidence/HG-047/../shared',
                                       'docs/exec-plans/evidence/HG-047'])
def test_relocation_refuses_foreign_cross_subtree_and_invalid_directory(repo, directory):
    root, base, before, source = captured(repo)
    snapshot = {p: p.read_bytes() for p in (root / 'docs').rglob('*') if p.is_file()}
    with pytest.raises(ValueError):
        ce.reencode(root, base, source, 'HG-047', [REF], RECODE, ce.XZ_FORMAT, directory)
    assert {p: p.read_bytes() for p in (root / 'docs').rglob('*') if p.is_file()} == snapshot
    assert (root / before['payload']).exists()


@pytest.mark.parametrize('collision', ['current', 'source', 'protected-base', 'symlink'])
def test_relocation_refuses_destination_collisions_before_any_writes(repo, collision):
    root, base = repo
    if collision == 'protected-base':
        p = root / CONSOLIDATED / 'occupied.json'
        p.parent.mkdir(parents=True)
        p.write_text('protected')
        base = commit(root)
    before = ce.capture(root, REF, b'1 passed\n', base, 'pytest', 0)
    destination = CONSOLIDATED + '/' + ce.digest((root / REF).read_bytes()) + '.json'
    p = root / destination
    p.parent.mkdir(parents=True, exist_ok=True)
    if collision == 'symlink':
        p.symlink_to(root / REF)
    elif collision in ('current', 'source'):
        p.write_text('collision')
    source = commit(root)
    if collision == 'source':
        p.unlink()
        commit(root)
    if collision == 'protected-base':
        # A protected payload destination is likewise prohibited even if the new
        # envelope would be absent. Pin the actual expected payload in the base.
        old = root / CONSOLIDATED / (before['raw_sha256'] + '.xz')
        old.write_bytes(ce.encode(b'1 passed\n', ce.XZ_FORMAT))
        base = commit(root)
        source = base
    original = (root / REF).read_bytes()
    with pytest.raises(ValueError):
        ce.reencode(root, base, source, 'HG-047', [REF], RECODE, ce.XZ_FORMAT, CONSOLIDATED)
    assert (root / REF).read_bytes() == original
    assert not (root / RECODE).exists()


def test_relocation_validation_failure_rolls_back_originals_and_new_destinations(repo, monkeypatch):
    root, base, before, source = captured(repo)
    original = (root / REF).read_bytes()
    payload = (root / before['payload']).read_bytes()
    def fail(*args, **kwargs):
        raise ValueError('simulated relocation validation failure')
    monkeypatch.setattr(ce, 'validate_reencoding', fail)
    with pytest.raises(ValueError, match='simulated'):
        ce.reencode(root, base, source, 'HG-047', [REF], RECODE, ce.XZ_FORMAT, CONSOLIDATED)
    assert (root / REF).read_bytes() == original
    assert (root / before['payload']).read_bytes() == payload
    assert not list((root / CONSOLIDATED).glob('*'))
    assert not (root / RECODE).exists()


def test_relocation_rejects_hidden_committed_destination_after_source(repo):
    root, base, _, source = captured(repo)
    destination = CONSOLIDATED + '/' + ce.digest((root / REF).read_bytes()) + '.json'
    p = root / destination
    p.parent.mkdir(parents=True)
    p.write_text('independent committed artifact')
    commit(root)
    p.unlink()
    before = (root / REF).read_bytes()
    with pytest.raises(ValueError, match='destination-collision'):
        ce.reencode(root, base, source, 'HG-047', [REF], RECODE, ce.XZ_FORMAT, CONSOLIDATED)
    assert (root / REF).read_bytes() == before
    assert not p.exists() and not (root / RECODE).exists()


@pytest.mark.parametrize('mutation', ['arbitrary-name', 'owner-root', 'retained-source'])
def test_handwritten_relocation_map_enforces_destination_shape_and_retirement(repo, mutation):
    root, base, _, record, _, _, refs, _ = relocated(repo)
    old = record['entries'][0]['replacement']['envelope']['path']
    if mutation == 'retained-source':
        source = record['source_revision']
        (root / refs[0]).write_bytes(ce.blob(root, refs[0], source))
    else:
        new = str(Path(old).with_name('arbitrary.json')) if mutation == 'arbitrary-name' else (
            'docs/exec-plans/evidence/HG-047/' + Path(old).name)
        (root / old).rename(root / new)
        record['entries'][0]['replacement']['envelope'] = ce.snapshot_bytes(new, (root / new).read_bytes())
        (root / RECODE).write_text(json.dumps(record))
    bad = commit(root)
    assert ce.audit(root, base, bad, 'HG-047')['errors']


def test_handwritten_map_cannot_overwrite_parent_destination(repo):
    root, base, original, source = captured(repo)
    record = ce.reencode(root, base, source, 'HG-047', [REF], RECODE, ce.XZ_FORMAT, CONSOLIDATED)
    replacement = record['entries'][0]['replacement']
    snapshots = {path: (root / path).read_bytes() for path in (
        replacement['envelope']['path'], replacement['payload']['path'], RECODE)}
    git(root, 'reset', '--hard', source)
    # Clear only fixture's untracked outputs from the uncommitted candidate.
    for path in snapshots:
        (root / path).unlink(missing_ok=True)
    destination = root / replacement['envelope']['path']
    destination.write_text('independent committed artifact')
    collision = commit(root)
    for path, data in snapshots.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_bytes(data)
    (root / REF).unlink()
    (root / original['payload']).unlink()
    bad = commit(root)
    assert any('destination-preexists' in error for error in ce.audit(root, base, bad, 'HG-047')['errors'])
    # A later unchanged suffix cannot erase the failed admission edge.
    (root / 'source').write_text('later')
    restored = commit(root)
    assert ce.audit(root, base, restored, 'HG-047')['errors']
    assert ce.blob(root, replacement['envelope']['path'], collision) == b'independent committed artifact'


@pytest.mark.parametrize('current', ['invalid-compact', 'directory', 'dangling-symlink',
                                     'parent-symlink', 'parent-file'])
def test_generic_review_availability_does_not_excuse_invalid_current_entry(repo, current):
    root, _, source, record, _, _, refs, _ = relocated(repo)
    original = root / refs[0]
    assert v.review_reference_available(root, refs[0], source)
    if current == 'invalid-compact':
        original.write_text(json.dumps({ce.MARKER: ce.FORMAT}))
    elif current == 'directory':
        original.mkdir()
    elif current == 'dangling-symlink':
        original.symlink_to(root / 'missing')
    else:
        original.parent.rmdir()
        if current == 'parent-symlink':
            original.parent.symlink_to(root / 'missing-parent')
        else:
            original.parent.write_text('not a directory')
    assert not v.review_reference_available(root, refs[0], source)
    assert not v.review_reference_available(root, '../outside', source)
    assert ce.read(root, record['entries'][0]['original']['envelope']['path'], source)


def advanced_base_conversion(repo):
    root, old_base, source, record, admission, _ = converted(repo)
    git(root, 'checkout', '-qb', 'protected-advance', old_base)
    (root / 'prerequisite').write_text('merged prerequisite')
    base = commit(root)
    git(root, 'checkout', '-qb', 'task-lineage', admission)
    git(root, 'merge', '-q', '--no-ff', '--no-edit', base)
    return root, old_base, source, record, admission, base, git(root, 'rev-parse', 'HEAD')


def test_retained_map_survives_normal_diverged_base_advance(repo):
    root, _, source, record, _, base, head = advanced_base_conversion(repo)
    data = (root / RECODE).read_bytes()
    assert ce.validate_reencoding(root, RECODE, record, base, head, 'HG-047')
    assert ce.audit(root, base, head, 'HG-047')['errors'] == []
    assert (root / RECODE).read_bytes() == data
    assert ce.read(root, REF, source) == ce.read(root, REF, head)


def test_new_writer_cannot_claim_pre_import_source(repo):
    root, old_base, _, source = captured(repo)
    git(root, 'checkout', '-qb', 'protected-advance', old_base)
    (root / 'prerequisite').write_text('merged prerequisite')
    base = commit(root)
    git(root, 'checkout', '-qb', 'task-lineage', source)
    git(root, 'merge', '-q', '--no-ff', '--no-edit', base)
    with pytest.raises(ValueError):
        ce.reencode(root, base, source, 'HG-047', [REF], RECODE, ce.XZ_FORMAT)
    assert not (root / RECODE).exists()


@pytest.mark.parametrize('side_branch', ['none', 'ordinary', 'reversed-parents'])
def test_handwritten_or_late_side_branch_map_after_base_import_rejects(repo, side_branch):
    root, old_base, _, source = captured(repo)
    git(root, 'checkout', '-qb', 'protected-advance', old_base)
    (root / 'prerequisite').write_text('merged prerequisite')
    base = commit(root)
    git(root, 'checkout', '-qb', 'task-lineage', source)
    git(root, 'merge', '-q', '--no-ff', '--no-edit', base)
    imported = git(root, 'rev-parse', 'HEAD')
    if side_branch != 'none':
        git(root, 'checkout', '-qb', 'late-map', source)
    record = ce.reencode(root, old_base, source, 'HG-047', [REF], RECODE, ce.XZ_FORMAT)
    map_head = commit(root)
    if side_branch == 'ordinary':
        git(root, 'checkout', '-q', 'task-lineage')
        assert git(root, 'rev-parse', 'HEAD') == imported
        git(root, 'merge', '-q', '--no-ff', '--no-edit', map_head)
    elif side_branch == 'reversed-parents':
        git(root, 'merge', '-q', '--no-ff', '--no-edit', imported)
    head = git(root, 'rev-parse', 'HEAD')
    with pytest.raises(ValueError):
        ce.validate_reencoding(root, RECODE, record, base, head, 'HG-047')
    assert ce.audit(root, base, head, 'HG-047')['errors']


def test_intermediate_base_import_cannot_grandfather_older_base_claim(repo):
    root, old_base, _, source = captured(repo)
    git(root, 'checkout', '-qb', 'protected-advance', old_base)
    (root / 'prerequisite').write_text('intermediate')
    intermediate = commit(root)
    git(root, 'checkout', '-qb', 'task-lineage', source)
    git(root, 'merge', '-q', '--no-ff', '--no-edit', intermediate)
    record = ce.reencode(root, old_base, source, 'HG-047', [REF], RECODE, ce.XZ_FORMAT)
    commit(root)
    git(root, 'checkout', '-q', 'protected-advance')
    (root / 'prerequisite').write_text('newest')
    base = commit(root)
    git(root, 'checkout', '-q', 'task-lineage')
    git(root, 'merge', '-q', '--no-ff', '--no-edit', base)
    head = git(root, 'rev-parse', 'HEAD')
    with pytest.raises(ValueError, match='retained-admission-base'):
        ce.validate_reencoding(root, RECODE, record, base, head, 'HG-047')
    assert ce.audit(root, base, head, 'HG-047')['errors']


@pytest.mark.parametrize('stage', ['before-import', 'after-import'])
@pytest.mark.parametrize('target', ['map', 'envelope', 'payload'])
def test_retained_map_transient_mutation_never_regains_admission(repo, stage, target):
    root, _, _, record, admission, base, _ = advanced_base_conversion(repo)
    if stage == 'before-import':
        git(root, 'reset', '--hard', admission)  # Synthetic fixture only.
    path = {'map': RECODE, 'envelope': REF,
            'payload': record['entries'][0]['replacement']['payload']['path']}[target]
    data = (root / path).read_bytes()
    (root / path).unlink()
    commit(root)
    (root / path).write_bytes(data)
    commit(root)
    if stage == 'before-import':
        git(root, 'merge', '-q', '--no-ff', '--no-edit', base)
    head = git(root, 'rev-parse', 'HEAD')
    assert ce.audit(root, base, head, 'HG-047')['errors']


def test_retained_map_rejects_protected_path_use_then_deletion(repo):
    root, old_base, _, record, admission, _, _ = advanced_base_conversion(repo)
    git(root, 'checkout', '-qb', 'protected-reuse', old_base)
    path = record['entries'][0]['replacement']['payload']['path']
    (root / path).parent.mkdir(parents=True, exist_ok=True)
    (root / path).write_bytes(b'protected artifact')
    commit(root)
    (root / path).unlink()
    base = commit(root)
    git(root, 'checkout', '-qb', 'reuse-task', admission)
    git(root, 'merge', '-q', '--no-ff', '--no-edit', base)
    head = git(root, 'rev-parse', 'HEAD')
    with pytest.raises(ValueError, match='retained-protected-path-history'):
        ce.validate_reencoding(root, RECODE, record, base, head, 'HG-047')
    assert ce.audit(root, base, head, 'HG-047')['errors']


@pytest.mark.parametrize('target', ['original', 'boundary-replacement'])
def test_retained_map_missing_bound_objects_fail_closed(repo, monkeypatch, target):
    root, _, source, record, admission, base, _ = advanced_base_conversion(repo)
    if target == 'original':
        original = ce.blob
        def missing(root_arg, path, revision, limit=None):
            if revision == source and path == REF:
                raise ValueError('unavailable original')
            return original(root_arg, path, revision, limit)
        monkeypatch.setattr(ce, 'blob', missing)
    else:
        git(root, 'reset', '--hard', admission)  # Synthetic fixture only.
        payload = record['entries'][0]['replacement']['payload']['path']
        data = (root / payload).read_bytes()
        (root / payload).unlink()
        commit(root)
        git(root, 'merge', '-q', '--no-ff', '--no-edit', base)
        (root / payload).write_bytes(data)
        commit(root)
    head = git(root, 'rev-parse', 'HEAD')
    assert ce.audit(root, base, head, 'HG-047')['errors']


def test_retained_map_does_not_authorize_foreign_owner(repo):
    root, _, _, _, _, base, head = advanced_base_conversion(repo)
    assert ce.audit(root, base, head, 'HG-048')['errors']


def test_retained_map_supports_later_base_advance_and_new_own_conversion(repo):
    root, _, source, _, _, base, head = advanced_base_conversion(repo)
    git(root, 'checkout', '-q', 'protected-advance')
    (root / 'prerequisite').write_text('next merged prerequisite')
    latest = commit(root)
    git(root, 'checkout', '-q', 'task-lineage')
    git(root, 'merge', '-q', '--no-ff', '--no-edit', latest)
    head = git(root, 'rev-parse', 'HEAD')
    assert ce.audit(root, latest, head, 'HG-047')['errors'] == []
    assert ce.read(root, REF, source) == ce.read(root, REF, head)
    second = REF.replace('run.json', 'next.json')
    ce.capture(root, second, b'new failed check\n', head, 'second check', 1)
    new_source = commit(root)
    new_map = RECODE.replace('/conversion/', '/next-conversion/')
    assert new_map != RECODE
    ce.reencode(root, latest, new_source, 'HG-047', [second], new_map, ce.XZ_FORMAT)
    final = commit(root)
    assert ce.audit(root, latest, final, 'HG-047')['errors'] == []


def test_retained_map_recreation_on_base_imported_side_branch_rejects(repo):
    root, old_base, source, record, admission, base, task_head = advanced_base_conversion(repo)
    git(root, 'checkout', '-qb', 'late-identical-map', source)
    git(root, 'merge', '-q', '--no-ff', '--no-edit', base)
    recreated = ce.reencode(root, old_base, source, 'HG-047', [REF], RECODE, ce.XZ_FORMAT)
    assert recreated == record
    late = commit(root)
    git(root, 'checkout', '-q', 'task-lineage')
    assert git(root, 'rev-parse', 'HEAD') == task_head
    git(root, 'merge', '-q', '--no-ff', '--no-edit', late)
    head = git(root, 'rev-parse', 'HEAD')
    assert git(root, 'merge-base', '--is-ancestor', admission, head) == ''
    with pytest.raises(ValueError, match='retained-source-import-before-admission'):
        ce.validate_reencoding(root, RECODE, record, base, head, 'HG-047')
    assert ce.audit(root, base, head, 'HG-047')['errors']


@pytest.mark.parametrize('raw', [
    b'envelope.get("kineticloop_evidence")',
    b'envelope["compact_reencoding"]',
    b'Quoted prose mentions "kineticloop_evidence" and "compact_reencoding".',
    b'{"ordinary": "kineticloop_evidence"}',
    b'"kineticloop_evidence"',
    b'envelope.get("payload"); envelope["raw_sha256"]; envelope["stored_sha256"]',
])
@pytest.mark.parametrize('codec', [None, ce.FORMAT, ce.XZ_FORMAT])
def test_ordinary_reserved_field_references_remain_lossless(repo, raw, codec):
    root, base = repo
    assert ce.envelope(raw) is None
    assert ce.reencoding_record(raw) is None
    if codec is None:
        (root / REF).parent.mkdir(parents=True)
        (root / REF).write_bytes(raw)
    else:
        ce.capture(root, REF, raw, base, 'pytest', 0, codec=codec)
    head = commit(root)
    assert ce.read(root, REF, head) == raw


def test_exact_original_reader_is_plain_and_history_compatible(repo):
    raw = (ROOT / 'docs/exec-plans/evidence/HG-056/original-reader.fixture').read_bytes()
    assert len(raw) == 8063
    assert ce.digest(raw) == 'a602ee684cdd7b4d8169388d2a2fe821fc6bc5beadf0d69a593c2ed260ffe382'
    root, base, _, source = captured(repo)
    path = root / 'docs/exec-plans/evidence/HG-047/reader.arbitrary'
    path.write_bytes(raw)
    source = commit(root)
    ce.reencode(root, base, source, 'HG-047', [REF], RECODE, ce.XZ_FORMAT)
    head = commit(root)
    assert ce.envelope(raw) is None and ce.reencoding_record(raw) is None
    assert ce.read(root, str(path.relative_to(root)), head) == raw
    errors, maps = ce.reencoding_audit(root, base, head, 'HG-047')
    assert errors == [] and RECODE in maps
    assert ce.audit(root, base, head, 'HG-047')['errors'] == []
    inherited_errors, inherited_maps = ce.reencoding_audit(root, head, head, 'HG-048')
    assert inherited_errors == [] and inherited_maps == {RECODE}


@pytest.mark.parametrize('raw', [
    br"record = {'kineticloop\x5fevidence': 'gzip-v1'}",
    br"record = {'kineticloop\U0000005fevidence': 'gzip-v1'}",
    b"record = {'kineticloop_' 'evidence': 'gzip-v1'}",
    b"record = {('kineticloop_''evidence'): 'gzip-v1'}",
    b'record = {"kineticloop_evidence": "gzip-v1"}',
    b"record = {'kineticloop_evidence': 'gzip-v1'}",
    b'kineticloop_evidence = "gzip-v1"',
    b'# {"kineticloop_evidence": "gzip-v1"}',
    b'prefix {"kineticloop_evidence":',
    b'{"kineticloop_evidence"',
    b'"{\\"compact_reencoding\\": \\"v1\\"}"',
    b'record = "{\\"kineticloop_evidence\\": \\"gzip-v1\\"}"',
    b"{'payload': 'missing', 'raw_sha256': 'x', 'stored_sha256': 'y'}",
    b"{'protected_base': 'x', 'source_revision': 'y', 'entries': []}",
    b"{'authorization': 'x', 'preserved_records': [], 'entries': []}",
    b'envelope.get("kineticloop_evidence")\n{"compact_reencoding":',
])
@pytest.mark.parametrize('encoding', ['utf-8', 'utf-16', 'utf-32'])
def test_source_looking_reserved_metadata_fails_closed(repo, raw, encoding):
    raw = raw.decode().encode(encoding)
    with pytest.raises(ValueError):
        ce.envelope(raw)
    with pytest.raises(ValueError):
        ce.reencoding_record(raw)


@pytest.mark.parametrize('identity', ['HG-047', 'KL-999'])
@pytest.mark.parametrize('suffix', ['py', 'json', 'txt', 'log', 'gz', 'xz', 'arbitrary'])
def test_reserved_classification_is_owner_and_suffix_independent(repo, identity, suffix):
    root, _ = repo
    path = f'docs/exec-plans/evidence/{identity}/reader.{suffix}'
    target = root / path
    target.parent.mkdir(parents=True)
    raw = b'envelope.get("kineticloop_evidence")'
    target.write_bytes(raw)
    revision = commit(root)
    assert ce.read(root, path, revision) == raw
    assert v.evidence_exists(root, path, revision)
    assert v.m3_evidence_bytes(root, {'path': path, 'revision': revision,
                                   'sha256': ce.digest(raw)}, revision) == raw
    target.write_bytes(b"record = {'kineticloop_evidence': 'gzip-v1'}")
    revision = commit(root)
    assert not v.evidence_exists(root, path, revision)
    with pytest.raises(ValueError):
        ce.read(root, path, revision)
