"""Revision-bound full preflight and protected-state audit for HG034."""
import ast
import hashlib
import importlib.util
import inspect
import json
import subprocess
from dataclasses import fields
from pathlib import Path

import yaml

ROOT = Path.cwd()
BASE = 'ff57a80feebd4e539f9af277e0dcb26d942bc3e0'
HEAD = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
print('base_commit=' + BASE)
print('tested_commit=' + HEAD)
for path in ['FROZEN_BASELINE.json', '05_KineticLoop_Protocol_v1.2_FROZEN.md',
             '04_KineticLoop_DB_Schema_Design_v0.2_FROZEN.md', 'src', 'migrations', 'tests/db',
             '.github', 'CURRENT_REQUIREMENT_SET.json', 'KineticLoop_Acceptance_Spec_v1.2.2.json',
             'KineticLoop_Integration_Acceptance_v0.1.json', 'KineticLoop_Evidence_Manifest_v0.1.json',
             'docs/exec-plans/completed', 'docs/exec-plans/integrations', 'docs/exec-plans/milestones',
             'docs/exec-plans/active/KL-024.md', 'docs/contracts']:
    subprocess.run(['git', 'diff', '--exit-code', BASE, HEAD, '--', path], check=True)
print('PASS frozen/product/prerequisite fixture/packet/result/evidence/CI/requirement state unchanged')
for path in ['KineticLoop_Harness_Backlog_v0.2.json', 'KineticLoop_Harness_Traceability_v0.3.json']:
    old = json.loads(subprocess.check_output(['git', 'show', BASE + ':' + path]))
    new = json.loads((ROOT / path).read_text())
    assert {k:v for k,v in old.items() if k != 'tasks'} == {k:v for k,v in new.items() if k != 'tasks'}
    assert [t for t in old['tasks'] if t['id'] != 'KL-025'] == [t for t in new['tasks'] if t['id'] != 'KL-025']
    before = next(t for t in old['tasks'] if t['id'] == 'KL-025')
    after = next(t for t in new['tasks'] if t['id'] == 'KL-025')
    assert set(after) == set(before)
    changed = {k for k in after if after[k] != before[k]}
    assert changed == {'entry_conditions', 'write_paths', 'checks_required_for_this_task', 'check_contracts'}
    assert after['write_paths'] == before['write_paths'] + ['tests/db/test_planning.py']
    assert after['depends_on'] == ['KL-024'] and after['status'] == 'NOT_STARTED'
    assert after['review_requirements'] == before['review_requirements'] == ['DB_CONCURRENCY', 'GENERAL', 'PROTOCOL']
    assert set(after['checks_required_for_this_task']) == set(before['checks_required_for_this_task']) | {'planning_fixture_namespace_isolation_pu'}
    for check in before['check_contracts']:
        current = next(c for c in after['check_contracts'] if c['check_id'] == check['check_id'])
        if check['check_id'] == 'planning_prerequisite_regressions_pass':
            assert current == {**check, 'command': 'KINETICLOOP_KL024_FIXTURE_OWNER=KL-025 ' + check['command']}
        else:
            assert current == check
print('PASS only exact namespace scope/check refinements; all residual semantics/hard dependency/review union preserved')
after = next(t for t in json.loads((ROOT / 'KineticLoop_Harness_Backlog_v0.2.json').read_text())['tasks'] if t['id'] == 'KL-025')
spec = importlib.util.spec_from_file_location('validator', ROOT / 'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec); spec.loader.exec_module(v)
assert v.ledger_definition_errors(after) == []
assert v.packet_errors(after, (ROOT / 'docs/exec-plans/active/KL-025.md').read_text()) == []
fixture = (ROOT / v.LEDGER_PLANNING_FIXTURE_PATH).read_bytes()
assert hashlib.sha256(fixture).hexdigest() == '1b962c360d5eacb2eaa01eb3a733986b32f2975fbd6053c2d85efac234a041b8'
assert subprocess.check_output(['git', 'show', BASE + ':' + v.LEDGER_PLANNING_FIXTURE_PATH]) == fixture
result = yaml.safe_load((ROOT / 'docs/exec-plans/completed/KL-024_RESULT.yaml').read_text())
assert result['task_status'] == result['task_checks_status'] == 'PASS'
assert len(result['commands_run']) == 13 and all(c['result'] == 'PASS' for c in result['commands_run'])
reviews = [json.loads((ROOT / f'docs/exec-plans/reviews/KL-024/{kind}.json').read_text())
           for kind in ['GENERAL','PROTOCOL','DB_CONCURRENCY']]
assert all(r['status'] == 'PASS' for r in reviews)
assert len({r['reviewed_head_sha'] for r in reviews}) == 1
reviewed = reviews[0]['reviewed_head_sha']
subprocess.run(['git', 'merge-base', '--is-ancestor', reviewed, BASE], check=True)
assert v.suffix_errors(ROOT, reviewed, '54c201fcb08f4686897c3b3bb44f34a43490471b', 'KL-024', 'review') == []
assert subprocess.check_output(['git', 'show', reviewed + ':docs/exec-plans/completed/KL-024_RESULT.yaml']) == (ROOT/'docs/exec-plans/completed/KL-024_RESULT.yaml').read_bytes()
assert subprocess.check_output(['git', 'show', BASE + '^2:tests/db/test_planning.py']) == fixture
print('PASS actual normal PR62 merge, result13 PASS, exact union review binding and allowed premerge suffix')
from kineticloop.persistence import planning as p
from kineticloop.db.lifecycle import DatabaseLifecycle
expected = {
 'PlanningIdentity':['actor','subject_id'],
 'AdmitOrReviseIntent':['subject_id','key','local_date','purpose','calendar_policy','constraints','explicit','trigger'],
 'AcquireLease':['subject_id','key','intent_id','expected_owner','expected_fence','request_revision','attempt_id','seconds'],
 'RenewLease':['subject_id','key','intent_id','fence','request_revision','attempt_id','seconds'],
}
for name, members in expected.items():
    assert [f.name for f in fields(getattr(p,name))] == members
    print('API '+name+' fields='+','.join(members))
for name in ['admit_or_revise','acquire_lease','renew_lease']:
    print('API '+name+' '+str(inspect.signature(getattr(p.PlanningWorkflowService,name))))
transactions = (ROOT/'src/kineticloop/persistence/transactions.py').read_text()
for literal in ['"limits": dict(limits)', '"reserved": {k: 0 for k in limits}',
                '"settled": {k: 0 for k in limits}', '"root_payload"] = dict(current[7])',
                '"UNKNOWN": "OUTCOME_UNKNOWN"', 'expected_attempt_id', 'expected_request_revision']:
    assert literal in transactions, literal
from kineticloop.persistence.transactions import RepositoryTransaction
fence = inspect.getsource(RepositoryTransaction.require_current_fence)
for literal in ["intent.subject_id=%s", "intent.lease_owner=%s AND intent.fence_token=%s",
                "intent.status='RUNNING'", "intent.lease_expires_at > clock_timestamp()",
                "intent.deadline > clock_timestamp()", "request.request_revision=%s",
                "intent.current_attempt_id=%s", "a.ref_s28_id=request.id"]:
    assert literal in fence, literal
print('PASS live guard binds subject/current request/attempt/owner/fence and strict trusted-time lease/deadline')
life = DatabaseLifecycle(ROOT, environ={'COMPOSE_PROJECT_NAME':'arbitrary', 'KINETICLOOP_DB_NAME':'arbitrary'})
assert life.environment['COMPOSE_PROJECT_NAME'] == life.namespace.project_name
assert life.environment['KINETICLOOP_DB_NAME'] == life.namespace.database_name
print('PASS actual root limits/reserved/settled payload and UNKNOWN vocabulary; generic env injection is inadequate')
for path in ['tests/unit/workflow/test_planning.py','tests/unit/persistence/test_transactions.py']:
    source = (ROOT/path).read_text()
    assert 'DatabaseLifecycle' not in source and 'bootstrap_two_phase' not in source
    print('FIXTURE '+path+' pure unit; no lifecycle')
for path, names in [
 ('tests/db/test_planning.py',['database_urls']),
 ('tests/db/test_transaction_interfaces.py',['database_urls','_reset_kl022_fixture','_seed_transaction_rows']),
 ('tests/db/test_migrations.py',['bootstrap_two_phase']),
 ('tests/db/test_safety_registry.py',['seed'])]:
    source=(ROOT/path).read_text(); tree=ast.parse(source)
    functions={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
    for name in names:
        assert name in functions
        print('FIXTURE '+path+':'+str(functions[name].lineno)+' '+name)
assert 'KINETICLOOP_KL022_COMPOSE_PROJECT' in (ROOT/'tests/db/test_transaction_interfaces.py').read_text()
assert 'KINETICLOOP_KL022_DATABASE' in (ROOT/'tests/db/test_transaction_interfaces.py').read_text()
assert 'database = lifecycle.reset()' in (ROOT/'tests/db/test_migrations.py').read_text()
print('PASS complete called fixture inventory: selected lifecycle -> bootstrap/role URLs -> seed/truncate -> same-project destroy')
print('LIMITATION KL024 result retains immutable premerge UNMERGED; actual merge recorded by Git. No KL024 integration artifact exists at base; HG034 does not create/change historical bookkeeping.')
print('LIMITATION candidate proof is prospective isolation/regression evidence only; all future KL025 implementation checks/product/release obligations NOT_RUN')
