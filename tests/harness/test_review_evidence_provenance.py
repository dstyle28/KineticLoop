"""Real Git provenance regressions for integration review evidence (HG043)."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('provenance_validator', ROOT / 'tools/harness/validate_harness.py')
assert SPEC and SPEC.loader
v = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(v)
OWN = 'docs/exec-plans/reviews/KL-001/'
TASK_EVIDENCE = 'docs/exec-plans/evidence/KL-001/check.log'


class History:
    def __init__(self, root: Path):
        self.root = root
        self.task = next(t for t in json.loads((ROOT / v.BACKLOG).read_text())['tasks'] if t['id'] == 'KL-001')
        self.git('init', '-q')
        self.put('src/kineticloop/cli.py', 'original\n')
        self.base = self.commit('baseline')
        result = {
            'task_identity': self.task['task_identity'], 'display_task_id': 'KL-001',
            'base_commit': self.base, 'tested_commit': self.base, 'task_status': 'PASS',
            'task_checks_status': 'PASS', 'integration_status': 'UNMERGED', 'summary': 'fixture',
            'files_changed': [], 'requirements_covered': [],
            'commands_run': [{'check_id': c, 'command': 'fixture ' + c, 'result': 'PASS',
                              'evidence_ref': TASK_EVIDENCE}
                             for c in self.task['checks_required_for_this_task']],
        }
        self.put(TASK_EVIDENCE)
        self.put(v.result_paths('KL-001')[1], json.dumps(result))
        self.reviewed = self.commit('result and task evidence before review')

    def git(self, *args: str) -> str:
        env = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
        return subprocess.check_output(
            ['git', '-c', 'user.name=Provenance Test', '-c', 'user.email=test@example.invalid',
             '-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=/dev/null',
             '-c', 'gc.auto=0', *args], cwd=self.root, env=env, stderr=subprocess.STDOUT,
        ).decode().strip()

    def put(self, path: str, text: str = 'evidence\n') -> Path:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        return target

    def commit(self, message: str) -> str:
        self.git('add', '.')
        self.git('commit', '-qm', message)
        return self.git('rev-parse', 'HEAD')

    def review(self, refs: list[str]) -> str:
        self.put(OWN + 'GENERAL.json', json.dumps({
            'task_identity': self.task['task_identity'], 'reviewed_head_sha': self.reviewed,
            'review_type': 'GENERAL', 'status': 'PASS', 'findings': [],
            'review_contract_version': 'v0.2', 'evidence_refs': refs,
        }))
        return self.commit('review record')

    def errors(self, review_commit: str, merge: str | None = None) -> list[str]:
        record = {
            'task_identity': self.task['task_identity'], 'display_task_id': 'KL-001',
            'result_commit': self.reviewed, 'reviewed_head_sha': self.reviewed,
            'review_record_commit': review_commit, 'merge_commit': merge or review_commit,
            'integration_status': 'MERGED',
        }
        schemas = [jsonschema.Draft202012Validator(json.loads((ROOT / name).read_text()))
                   for name in (v.INTEGRATION_SCHEMA, 'THREAD_RESULT.schema.json', 'THREAD_REVIEW.schema.json')]
        return v.integration_record_errors(
            self.root, Path('KL-001.json'), record, *schemas, {'KL-001': self.task})

    def commit_tree(self, treeish: str, parents: list[str]) -> str:
        args = ['commit-tree', self.git('rev-parse', treeish + '^{tree}')]
        for parent in parents:
            args.extend(['-p', parent])
        return self.git(*args, '-m', 'synthetic merge')


@pytest.fixture
def history(tmp_path: Path) -> History:
    return History(tmp_path)


def test_ordinary_and_review_created_refs_bind_exact_revisions(history: History) -> None:
    ref = OWN + 'independent.log'
    history.put(ref)
    review = history.review([TASK_EVIDENCE, v.result_paths('KL-001')[1],
                             'src/kineticloop/cli.py', ref])
    assert not v.revision_regular_file(history.root, ref, history.reviewed)
    assert v.revision_regular_file(history.root, ref, review)
    assert history.errors(review) == []
    # Even deletion/change at ambient HEAD cannot change the committed source binding.
    (history.root / ref).unlink()
    history.put(TASK_EVIDENCE, 'ambient modified\n')
    assert history.errors(review) == []


@pytest.mark.parametrize('ref', [
    '../review.log', '/tmp/review.log', OWN + '../KL-002/log', OWN + './log',
    OWN + '/log', OWN + 'nested/../../KL-002/log', OWN + 'log\\name', OWN + 'log\0name',
    'docs/exec-plans/reviews/KL-001A/log', 'docs/exec-plans/reviews/KL-002/log',
    'docs/exec-plans/evidence/KL-001/later.log', 'src/kineticloop/later.py',
    'docs/exec-plans/completed/KL-001_RESULT.yaml', OWN + 'missing.log',
])
def test_unscoped_or_non_normalized_or_missing_refs_rejected(history: History, ref: str) -> None:
    if v.relative_path(ref) and '\0' not in ref and not ref.endswith('missing.log'):
        history.put(ref)
    review = history.review([ref])
    assert any(e.startswith('integration-review-evidence:') for e in history.errors(review))


@pytest.mark.parametrize('mode', ['directory', 'symlink'])
@pytest.mark.parametrize('before_review', [False, True])
def test_only_regular_blobs_are_evidence(history: History, mode: str, before_review: bool) -> None:
    ref = OWN + 'nonregular'
    if mode == 'directory':
        history.put(ref + '/child')
    else:
        path = history.root / ref
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to('../../../evidence/KL-001/check.log')
    if before_review:
        history.reviewed = history.commit('nonregular before review')
    review = history.review([ref])
    assert any(e.startswith('integration-review-evidence:') for e in history.errors(review))


def test_later_boundless_additions_do_not_supply_review_refs(history: History) -> None:
    ref = OWN + 'later.log'
    review = history.review([ref])
    history.put(ref)
    history.commit('unbound later evidence')
    assert any(e.startswith('integration-review-evidence:') for e in history.errors(review))


@pytest.mark.parametrize('path', ['src/kineticloop/cli.py', TASK_EVIDENCE,
                                'docs/exec-plans/completed/KL-001_RESULT.json',
                                'docs/exec-plans/reviews/KL-001A/log'])
def test_content_change_then_revert_is_not_a_review_only_suffix(history: History, path: str) -> None:
    target = history.root / path
    old = target.read_bytes() if target.exists() else None
    history.put(path, 'changed\n')
    history.commit('intervening forbidden change')
    if old is None:
        target.unlink()
    else:
        target.write_bytes(old)
    history.commit('revert forbidden change')
    ref = OWN + 'independent.log'
    history.put(ref)
    review = history.review([ref])
    errors = history.errors(review)
    assert 'integration-review-stale-change:' + path in errors
    assert any(e.startswith('integration-review-evidence:') for e in errors)


def test_task_checks_cannot_use_post_review_bookkeeping(history: History) -> None:
    result_path = v.result_paths('KL-001')[1]
    result = json.loads((history.root / result_path).read_text())
    ref = OWN + 'task-check.log'
    for command in result['commands_run']:
        command['evidence_ref'] = ref
    history.put(result_path, json.dumps(result))
    history.reviewed = history.commit('result claims future reviewer log')
    history.put(ref)
    review = history.review([ref])
    assert any(e.startswith('integration-result-semantic:KL-001:') for e in history.errors(review))


def test_nonlinear_review_suffix_is_rejected_even_with_equal_tree(history: History) -> None:
    ref = OWN + 'independent.log'
    history.put(ref)
    linear = history.review([ref])
    side = history.commit_tree(history.reviewed, [history.base])
    merge = history.commit_tree(linear, [linear, side])
    history.git('checkout', '-q', '--detach', merge)
    errors = history.errors(merge)
    assert any(e.startswith('integration-review-suffix-merge:') for e in errors)
    assert any(e.startswith('integration-review-evidence:') for e in errors)


def test_nonancestor_record_cannot_use_exact_tree_shortcut(history: History) -> None:
    ref = OWN + 'independent.log'
    history.put(ref)
    review = history.review([ref])
    sibling = history.commit_tree(review, [history.base])
    history.git('checkout', '-q', '--detach', sibling)
    errors = history.errors(sibling)
    assert 'integration-ancestry:KL-001:reviewed-to-review-record' in errors
    assert any(e.startswith('integration-review-evidence:') for e in errors)


def test_exact_tree_squash_preserves_review_created_binding(history: History) -> None:
    ref = OWN + 'independent.log'
    history.put(ref)
    review = history.review([ref])
    squash = history.commit_tree(review, [history.base])
    history.git('checkout', '-q', '--detach', squash)
    assert history.errors(review, squash) == []
    history.put('unrelated.txt')
    different = history.commit('near match')
    assert 'integration-ancestry-or-exact-tree:KL-001:review-to-merge' in history.errors(review, different)


def test_delayed_review_ordinary_refs_preserved_but_new_exception_strict(history: History) -> None:
    merge = history.reviewed
    history.put('unrelated.txt')
    history.commit('later unrelated task')
    ordinary = history.review([TASK_EVIDENCE])
    assert history.errors(ordinary, merge) == []
    ref = OWN + 'independent.log'
    history.put(ref)
    review = history.review([TASK_EVIDENCE, ref])
    assert any(e.startswith('integration-review-evidence:') for e in history.errors(review, merge))


def test_delayed_review_with_only_own_linear_append_accepts_created_log(history: History) -> None:
    merge = history.reviewed
    ref = OWN + 'independent.log'
    history.put(ref)
    review = history.review([ref])
    assert history.errors(review, merge) == []


def test_delayed_unrelated_merge_does_not_widen_created_evidence(history: History) -> None:
    merged = history.reviewed
    history.put('unrelated.txt')
    later = history.commit('later unrelated work')
    side = history.commit_tree(history.reviewed, [history.reviewed])
    reintegrated = history.commit_tree(later, [later, side])
    history.git('checkout', '-q', '--detach', reintegrated)
    ordinary = history.review([TASK_EVIDENCE])
    assert history.errors(ordinary, merged) == []
    ref = OWN + 'independent.log'
    history.put(ref)
    review = history.review([ref])
    assert any(e.startswith('integration-review-evidence:') for e in history.errors(review, merged))


def test_changed_task_check_evidence_after_review_stays_stale(history: History) -> None:
    history.put(TASK_EVIDENCE, 'forged replacement\n')
    history.commit('replace task check evidence')
    review = history.review([TASK_EVIDENCE])
    assert 'integration-review-stale-change:' + TASK_EVIDENCE in history.errors(review)


def test_executable_regular_blob_with_literal_unusual_name(history: History) -> None:
    ref = OWN + 'a [literal]: log.py'
    target = history.put(ref)
    target.chmod(0o755)
    review = history.review([ref])
    assert history.errors(review) == []


def test_multiple_own_review_appends_bind_the_recorded_endpoint(history: History) -> None:
    ref = OWN + 'independent.log'
    history.put(ref, 'first reviewer draft\n')
    history.commit('first own review append')
    history.put(ref, 'final reviewer log\n')
    endpoint = history.review([ref])
    assert history.errors(endpoint) == []
    history.put(ref, 'later unbound replacement\n')
    history.commit('later own bookkeeping')
    assert history.errors(endpoint) == []
    assert v.git(history.root, 'show', endpoint + ':' + ref) == b'final reviewer log\n'


@pytest.mark.parametrize('kind', ['symlink', 'directory', 'gitlink'])
def test_present_nonregular_entry_cannot_be_replaced_through_exception(
        history: History, kind: str) -> None:
    ref = OWN + 'present'
    target = history.root / ref
    if kind == 'gitlink':
        history.git('update-index', '--add', '--cacheinfo', f'160000,{history.base},{ref}')
        history.git('commit', '-qm', 'reviewed gitlink entry')
        history.reviewed = history.git('rev-parse', 'HEAD')
    else:
        if kind == 'directory':
            history.put(ref + '/child')
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to('../../../evidence/KL-001/check.log')
        history.reviewed = history.commit('reviewed nonregular entry')
        if kind == 'directory':
            (target / 'child').unlink()
            target.rmdir()
        else:
            target.unlink()
    assert v.revision_git_entry(history.root, ref, history.reviewed) is not None
    assert not v.evidence_exists(history.root, ref, history.reviewed)
    assert not v.revision_regular_file(history.root, ref, history.reviewed)
    history.put(ref, 'review-only replacement\n')
    review = history.review([ref])
    assert v.suffix_errors(history.root, history.reviewed, review, 'KL-001', 'review') == []
    assert v.revision_regular_file(history.root, ref, review)
    assert 'integration-review-evidence:KL-001:GENERAL:' + ref in history.errors(review)


@pytest.mark.parametrize('source', ['reviewed', 'review_record'])
def test_missing_blob_is_not_available_evidence_or_an_absent_path(
        history: History, source: str) -> None:
    ref = OWN + 'unique-object.log'
    if source == 'reviewed':
        history.put(ref, 'unique original reviewed blob\n')
        history.reviewed = history.commit('ordinary reviewed evidence')
        oid = history.git('rev-parse', history.reviewed + ':' + ref)
        history.put(ref, 'replacement cannot supply missing reviewed blob\n')
        review = history.review([ref])
        bound = history.reviewed
    else:
        history.put(ref, 'unique review-created blob\n')
        review = history.review([ref])
        oid = history.git('rev-parse', review + ':' + ref)
        bound = review
    # Corrupt only this isolated fixture's loose object; never the real repository.
    object_path = history.root / '.git/objects' / oid[:2] / oid[2:]
    assert history.root.resolve() in object_path.resolve().parents
    object_path.unlink()
    assert v.revision_git_entry(history.root, ref, bound) is not None
    assert not v.revision_regular_file(history.root, ref, bound)
    assert 'integration-review-evidence:KL-001:GENERAL:' + ref in history.errors(review)


@pytest.mark.parametrize('removed_marker', [False, True])
def test_archival_mapping_cannot_supply_review_record_evidence(tmp_path, removed_marker):
    history = History(tmp_path)
    ce = v.compact_evidence
    metadata = ce.historical_template()
    metadata['entries'] = []
    if removed_marker:
        metadata.pop(ce.MARKER)
    ref = OWN + 'raw/archival.log'
    history.put(ref, json.dumps(metadata))
    record_commit = history.review([ref])
    assert not v.review_evidence_exists(history.root, ref, history.reviewed,
                                        record_commit, 'KL-001', True)
    assert any('integration-review-evidence' in error for error in history.errors(record_commit))


@pytest.mark.parametrize('codec', ['gzip-v1', 'xz-v1'])
def test_compact_review_created_bound_revision_and_suffix(tmp_path, codec):
    history = History(tmp_path)
    ce = v.compact_evidence
    ref = OWN + 'raw/run.json'
    ce.capture(history.root, ref, b'1 passed\n', history.base, 'pytest', 0, codec=codec)
    review = history.review([ref])
    assert v.review_evidence_exists(history.root, ref, history.reviewed, review, 'KL-001', True)
    assert not v.review_evidence_exists(history.root, ref, history.reviewed, review, 'KL-001', False)
    assert not v.review_evidence_exists(history.root, ref, history.reviewed, review, 'KL-001A', True)
    manifest = json.loads((history.root / ref).read_text())
    (history.root / manifest['payload']).unlink()
    later = history.commit('deleted later payload')
    assert not v.review_evidence_exists(history.root, ref, history.reviewed, later, 'KL-001', True)
    assert v.review_evidence_exists(history.root, ref, history.reviewed, review, 'KL-001', True)


@pytest.mark.parametrize('identity', ['KL-001', 'HG-054'])
@pytest.mark.parametrize('kind', ['tested', 'review'])
@pytest.mark.parametrize('restore', [False, True])
def test_compact_conversion_never_uses_bookkeeping_suffix(tmp_path, identity, kind, restore):
    history = History(tmp_path)
    ce = v.compact_evidence
    directory = 'reviews' if kind == 'review' else 'evidence'
    ref = f'docs/exec-plans/{directory}/{identity}/raw/run.json'
    record_path = f'docs/exec-plans/{directory}/{identity}/conversion/COMPACT_REENCODING.json'
    before = ce.capture(history.root, ref, b'1 failed\n', history.base, 'pytest', 1)
    source = history.commit('compact output before tested or reviewed revision')
    original = {path: (history.root / path).read_bytes() for path in (ref, before['payload'])}
    ce.reencode(history.root, history.base, source, identity, [ref], record_path, ce.XZ_FORMAT)
    head = history.commit('conversion inside bookkeeping paths')
    if restore:
        for path in (history.root / ref).parent.glob('*.xz'):
            path.unlink()
        (history.root / record_path).unlink()
        for path, data in original.items():
            (history.root / path).write_bytes(data)
        head = history.commit('restored conversion cannot repair stale review or test')
    suffix = v.governance_suffix_errors if identity.startswith('HG-') else v.suffix_errors
    assert any('representation-mutation' in error for error in
               suffix(history.root, source, head, identity, kind))
