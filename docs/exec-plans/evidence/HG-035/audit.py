"""Revision-bound HG035 protected-state, actual merged dependency and API audit."""
import ast
import hashlib
import importlib.util
import inspect
import json
import subprocess
from dataclasses import fields
from pathlib import Path

import jsonschema
import yaml

ROOT = Path.cwd()
BASE = 'eab2b305351cf3c504f74ac74868edc58d0a3430'
HEAD = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
print('base_commit=' + BASE)
print('tested_commit=' + HEAD)

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)

spec = importlib.util.spec_from_file_location('hg035_validator', ROOT / 'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
for path in ['src', 'migrations', 'tests/db', 'tests/unit', '.github', 'compose.yaml',
             'FROZEN_BASELINE.json', '05_KineticLoop_Protocol_v1.2_FROZEN.md',
             '04_KineticLoop_DB_Schema_Design_v0.2_FROZEN.md', 'CURRENT_REQUIREMENT_SET.json',
             'KineticLoop_Acceptance_Spec_v1.2.2.json', 'KineticLoop_Integration_Acceptance_v0.1.json',
             'KineticLoop_Evidence_Manifest_v0.1.json', 'docs/exec-plans/completed',
             'docs/exec-plans/reviews/KL-024', 'docs/exec-plans/reviews/KL-025',
             'docs/exec-plans/milestones', 'docs/contracts', 'docs/exec-plans/active/KL-024.md',
             'docs/exec-plans/active/KL-025.md']:
    assert git('diff', '--name-only', BASE, 'HEAD', '--', path) == b'', path
print('PASS frozen/product/CI/requirement/completed prerequisites preserved byte-for-byte')
for path in [v.BACKLOG, v.TRACEABILITY]:
    old = json.loads(git('show', BASE + ':' + path))
    new = json.loads((ROOT / path).read_text())
    assert {k: x for k, x in old.items() if k != 'tasks'} == {k: x for k, x in new.items() if k != 'tasks'}
    assert [t for t in old['tasks'] if t['id'] != 'KL-019'] == [t for t in new['tasks'] if t['id'] != 'KL-019']
    task = next(t for t in new['tasks'] if t['id'] == 'KL-019')
    assert task['status'] == 'NOT_STARTED'
    assert task['requirements_covered'] == ['I01', 'I02', 'I04', 'I07', 'A03@DC']
    assert task['depends_on'] == ['KL-017', 'KL-020', 'KL-021', 'KL-022', 'KL-023', 'KL-024', 'KL-025']
    assert task['review_requirements'] == ['DB_CONCURRENCY', 'GENERAL', 'PROTOCOL']
print('PASS only unstarted KL019 definitions refined; dependency/review union and product state preserved')
backlog = json.loads((ROOT / v.BACKLOG).read_text())
tasks = {t['id']: t for t in backlog['tasks']}
task = tasks['KL-019']
assert v.execution_definition_errors(task) == []
assert v.packet_errors(task, (ROOT / 'docs/exec-plans/active/KL-019.md').read_text()) == []
assert v.traceability_projection(task) == next(t for t in json.loads((ROOT / v.TRACEABILITY).read_text())['tasks'] if t['id'] == 'KL-019')
assert len(task['check_contracts']) == len(task['checks_required_for_this_task']) == 20
assert not v.result_paths_at_revision(ROOT, 'KL-019', BASE)
assert not any((ROOT / p).exists() for p in v.result_paths('KL-019'))
print('PASS exact20 check contracts, narrow write/resources/environment, guarded identity/bootstrap/owner boundaries')
for tid in ['KL-015', 'KL-017', 'KL-020', 'KL-021', 'KL-022', 'KL-023', 'KL-024', 'KL-025']:
    result_path = v.result_paths_at_revision(ROOT, tid, BASE)
    assert len(result_path) == 1, tid
    result = yaml.safe_load(git('show', BASE + ':' + result_path[0]))
    assert result['task_status'] == result['task_checks_status'] == 'PASS'
    reviewed = []
    for kind in tasks[tid]['review_requirements']:
        review = json.loads(git('show', BASE + f':docs/exec-plans/reviews/{tid}/{kind}.json'))
        assert review['status'] == 'PASS' and review['task_identity'] == tasks[tid]['task_identity']
        reviewed.append(review['reviewed_head_sha'])
    assert len(set(reviewed)) == 1, tid
    subprocess.run(['git', 'merge-base', '--is-ancestor', reviewed[0], BASE], check=True)
    assert git('show', reviewed[0] + ':' + result_path[0]) == git('show', BASE + ':' + result_path[0])
    print('MERGED_PREREQUISITE', tid, 'tested=' + result['tested_commit'], 'reviewed=' + reviewed[0])
schema = lambda p: jsonschema.Draft202012Validator(json.loads((ROOT / p).read_text()))
for tid in ['KL-024', 'KL-025']:
    path = ROOT / f'docs/exec-plans/integrations/{tid}.json'
    record = json.loads(path.read_text())
    issues = v.integration_record_errors(ROOT, path, record, schema('INTEGRATION_RECORD.schema.json'),
                                        schema('THREAD_RESULT.schema.json'), schema('THREAD_REVIEW.schema.json'), tasks)
    assert not issues, issues
    assert len(git('rev-list', '--parents', '-n', '1', record['merge_commit']).split()) == 3
    assert v.suffix_errors(ROOT, record['reviewed_head_sha'], record['review_record_commit'], tid, 'review') == []
    print('NORMAL_MERGED_INTEGRATION', tid, json.dumps(record, sort_keys=True))
print('PASS normal actual KL024/KL025 merge ancestry, byte-identical results, selected evidence and review-only suffix')
from kineticloop.contracts.commands import PublishManifest, StrictCommand, TransactionBoundary
from kineticloop.persistence import planning as planning
from kineticloop.persistence import call_ledger as ledger
from kineticloop.persistence.factsets import BuilderIdentity
from kineticloop.persistence.transactions import TRANSACTION_OWNER_MATRIX, MUTATION_CAPABILITY_MATRIX, RepositoryTransaction
assert PublishManifest.allowed_test_boundaries == {TransactionBoundary.T6, TransactionBoundary.T7}
assert StrictCommand.allowed_test_boundaries == {TransactionBoundary.T6, TransactionBoundary.T7}
for cls in [BuilderIdentity, planning.PlanningIdentity, planning.AdmitOrReviseIntent,
            planning.AcquireLease, planning.RenewLease]:
    print('API', cls.__name__, 'fields=' + ','.join(f.name for f in fields(cls)))
for cls, methods in [(planning.PlanningWorkflowService, ['admit_or_revise', 'acquire_lease', 'renew_lease']),
                     (ledger.CallLedgerService, ['reserve', 'permit', 'cancel', 'mark_unknown', 'settle'])]:
    for name in methods:
        print('API', cls.__name__ + '.' + name, inspect.signature(getattr(cls, name)))
for kind in ['PublishManifest', 'CommitBundle', 'StartSession']:
    owner = TRANSACTION_OWNER_MATRIX[kind]
    assert owner.registry_required
    print('OWNER', kind, owner.owner, owner.boundary, owner.mutation_surfaces)
assert 'AdvanceAttempt' not in TRANSACTION_OWNER_MATRIX and 'RecordSnapshot' not in TRANSACTION_OWNER_MATRIX
assert 'daily head does not exist' in inspect.getsource(RepositoryTransaction.lock_daily_head)
assert 'session lifecycle or repeated START guard failed' in inspect.getsource(RepositoryTransaction.lock_execution)
assert 'COMMIT_READY' in inspect.getsource(RepositoryTransaction.prepare_authorization_basis)
print('PASS strict TEST_ONLY T6/T7 wire, existing owner matrix and bounded first-use/upstream gaps verified')
for path in ['tests/db/test_transaction_interfaces.py', 'tests/db/test_planning.py', 'tests/db/test_call_ledger.py',
             'tests/db/test_migrations.py', 'tests/db/test_safety_registry.py',
             'tests/unit/persistence/test_transactions.py', 'tests/unit/workflow/test_planning.py',
             'tests/unit/workflow/test_call_ledger.py']:
    raw = (ROOT / path).read_bytes()
    assert raw == git('show', BASE + ':' + path)
    tree = ast.parse(raw)
    funcs = [(n.name, n.lineno) for n in tree.body if isinstance(n, ast.FunctionDef)]
    print('FIXTURE_SOURCE', path, 'sha256=' + hashlib.sha256(raw).hexdigest(), 'functions=' + repr(funcs))
    if path.startswith('tests/unit/'):
        assert 'DatabaseLifecycle' not in raw.decode() and 'bootstrap_two_phase' not in raw.decode()
for path in v.EXECUTION_FIXTURE_BASE_HASHES:
    before = (ROOT / path).read_bytes()
    after = v.execution_fixture_candidate(path, before)
    assert v.execution_fixture_content_errors(path, before, after) == []
    print('EXACT_FUTURE_FIXTURE', path, 'before=' + hashlib.sha256(before).hexdigest(),
          'after=' + hashlib.sha256(after).hexdigest())
transaction_fixture = (ROOT / 'tests/db/test_transaction_interfaces.py').read_text()
assert 'KINETICLOOP_KL022_COMPOSE_PROJECT' in transaction_fixture
assert 'KINETICLOOP_KL022_DATABASE' in transaction_fixture
print('PASS complete actual fixture inventory; transaction fixture unchanged with existing two overrides')
print('LIMITATION governance PASS is not KL019 task/product PASS; all20 future checks and I01/I02/I04/I07/A03@DC obligations remain NOT_RUN')
print('HG035_AUDIT_PASS')
