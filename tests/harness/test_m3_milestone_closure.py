"""Synthetic isolated Git chains for prospective M3 closure; never project evidence."""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import subprocess
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('m3_validator', ROOT / 'tools/harness/validate_harness.py')
assert SPEC and SPEC.loader
v = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(v)
SCHEMAS = [jsonschema.Draft202012Validator(json.loads((ROOT / name).read_text())) for name in (
    v.MILESTONE_CLOSURE_SCHEMA, v.INTEGRATION_SCHEMA,
    'THREAD_RESULT.schema.json', 'THREAD_REVIEW.schema.json')]


class History:
    def __init__(self, root: Path):
        self.root = root
        subprocess.run(['git', 'clone', '-q', '--shared', '--no-hardlinks', str(ROOT), str(root)],
                       check=True, capture_output=True)
        self.git('checkout', '-q', '9268fc8dd8c071c02dc5c698274dbf6fcd112776')
        self.backlog = json.loads((root / v.BACKLOG).read_text())
        self.tasks = {t['id']: t for t in self.backlog['tasks']}
        self.records: dict[str, dict] = {}
        for name in ('KL-028', 'KL-029'):
            self.make_task(name)
        pending = list(v.M3_TASK_IDS | {'KL-074'})
        while pending:
            name = pending.pop()
            if name in self.records:
                continue
            self.records[name] = json.loads((root / f'docs/exec-plans/integrations/{name}.json').read_text())
            pending.extend(self.tasks[name]['depends_on'])
        self.tested = self.git('rev-parse', 'HEAD')
        self.change = 'HG-999'
        self.prefix = 'docs/exec-plans/evidence/HG-999/'
        self.payload = {'change_id': self.change, 'tested_commit': self.tested, 'status': 'PASS',
                        'commands': v.M3_REGRESSION_COMMANDS, 'executions': []}
        for i, command in enumerate(v.M3_REGRESSION_COMMANDS):
            run = {'command': command, 'tested_commit': self.tested, 'exit_code': 0}
            run['stdout'] = self.raw(f'{i}.log', 'HARNESS_CHECK_PASS\n' if command.endswith('check-harness') else '1 passed in 0.1s\n')
            if not command.endswith('check-harness'):
                selector = ('tests/unit/example.py::test_example' if command.endswith('test-unit')
                            else 'tests/harness/example.py::test_example' if command.endswith('test-harness')
                            else command.removeprefix('uv run pytest -q ').split()[0])
                if '::' not in selector:
                    selector += '::test_example'
                parts = selector.split('::')
                classname = '.'.join([parts[0].removesuffix('.py').replace('/', '.'), *parts[1:-1]])
                run['junit'] = self.raw(f'{i}.xml', f'<testsuite><testcase classname="{classname}" name="{parts[-1]}"/></testsuite>')
                selectors = ('tests/unit' if command.endswith('test-unit') else 'tests/harness'
                             if command.endswith('test-harness') else command.removeprefix('uv run pytest -q '))
                collection = {'command': 'uv run pytest --collect-only -q ' + selectors,
                              'tested_commit': self.tested, 'exit_code': 0, 'nodeids': [selector],
                              'stdout': self.raw(f'{i}-collect.log', selector + '\n1 test collected in 0.1s\n')}
                run['collection'] = self.raw(f'{i}-collect.json', json.dumps(collection))
            self.payload['executions'].append(run)
        self.regression_path = self.prefix + 'm3-regression-' + self.tested[:7] + '.json'
        self.put(self.regression_path, json.dumps(self.payload))
        self.evaluated = self.commit('synthetic fresh integrated regression evidence')
        self.closure = self.build_closure()

    def git(self, *args: str) -> str:
        env = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
        return subprocess.check_output(['git', '-c', 'user.name=M3 Fixture', '-c',
                                       'user.email=test@example.invalid', '-c', 'commit.gpgsign=false',
                                       '-c', 'core.hooksPath=/dev/null', '-c', 'gc.auto=0', *args],
                                      cwd=self.root, env=env, stderr=subprocess.STDOUT).decode().strip()

    def put(self, path: str, content: str) -> Path:
        p = self.root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return p

    def commit(self, message: str) -> str:
        self.git('add', '.')
        self.git('commit', '-qm', message)
        return self.git('rev-parse', 'HEAD')

    def evidence(self, path: str, revision: str) -> dict:
        return {'path': path, 'revision': revision,
                'sha256': v.blob_sha_at_revision(self.root, path, revision)}

    def raw(self, path: str, content: str) -> dict:
        path = self.prefix + path
        self.put(path, content)
        return {'path': path, 'sha256': v.sha(self.root / path)}

    def make_task(self, name: str) -> None:
        task = self.tasks[name]
        base = self.git('rev-parse', 'HEAD')
        commands = []
        for c in task['check_contracts']:
            ref = f'docs/exec-plans/evidence/{name}/{c["check_id"]}.log'
            self.put(ref, '1 passed in 0.1s\n')
            commands.append(dict(check_id=c['check_id'], command=c['command'], result='PASS', evidence_ref=ref))
        result = dict(task_identity=task['task_identity'], display_task_id=name, base_commit=base,
                      tested_commit=base, task_status='PASS', task_checks_status='PASS',
                      integration_status='UNMERGED', summary='synthetic validator data only',
                      commands_run=commands, requirements_covered=[], files_changed=[])
        self.put(v.result_paths(name)[0], json.dumps(result))
        reviewed = self.commit('synthetic task result and test evidence')
        for kind in task['review_requirements']:
            self.put(f'docs/exec-plans/reviews/{name}/{kind}.json', json.dumps(dict(
                task_identity=task['task_identity'], reviewed_head_sha=reviewed, review_type=kind,
                status='PASS', findings=[], review_contract_version='v0.2',
                evidence_refs=[v.result_paths(name)[0]])))
        review = self.commit('synthetic independent review suffix')
        record = dict(task_identity=task['task_identity'], display_task_id=name, result_commit=reviewed,
                      reviewed_head_sha=reviewed, review_record_commit=review, merge_commit=review,
                      integration_status='MERGED')
        self.put(f'docs/exec-plans/integrations/{name}.json', json.dumps(record))
        self.commit('synthetic merged integration bookkeeping')

    def build_closure(self):
        def integration(name):
            return dict(task_identity='harness-backlog-v0.2/' + name, display_task_id=name,
                        integration_record=f'docs/exec-plans/integrations/{name}.json',
                        sha256=v.sha(self.root / f'docs/exec-plans/integrations/{name}.json'))
        exits = []
        for exit_id, mapping in v.M3_EXIT_TASK_CHECKS.items():
            witnesses = []
            for name, ids in mapping.items():
                reviewed = self.records[name]['reviewed_head_sha']
                path = v.result_paths_at_revision(self.root, name, reviewed)[0]
                result = v.load_artifact_at_revision(self.root, path, reviewed)
                contracts = {c['check_id']: c for c in self.tasks[name]['check_contracts']}
                commands = {c['check_id']: c for c in result['commands_run']}
                for check in ids:
                    witnesses.append(dict(task_identity='harness-backlog-v0.2/' + name, check_id=check,
                                          tested_commit=result['tested_commit'], result='PASS',
                                          command=commands[check]['command'],
                                          oracle_sha256=v.canonical_value_sha(contracts[check]['pass_oracle']),
                                          result_artifact=self.evidence(path, reviewed),
                                          raw=self.evidence(commands[check]['evidence_ref'], reviewed)))
            exits.append(dict(check_id=exit_id, result='PASS', task_checks=witnesses))
        rows = v.packet_json_section((self.root / 'docs/exec-plans/active/KL-028.md').read_text(), 'Boundary layer ledger')
        for row in rows:
            if row['disposition'] == 'KL028_PLANNED_EXECUTABLE':
                row['status'] = 'PASS'
        interleavings = [dict(requirement_id=f'I{i:02}', layer='DC', status='PASS',
                             task_identity='harness-backlog-v0.2/KL-026', check_id=f'i{i:02}_dc') for i in range(1, 10)]
        interleavings.append(dict(requirement_id='I04', layer='WF', status='NOT_RUN',
                                  required_future_owner='M4 worker/fault process evidence'))
        return dict(milestone_identity='harness-backlog-v0.2/M3', display_milestone_id='M3',
                    closure_status='PASS', evaluated_commit=self.evaluated,
                    integrations=[integration(n) for n in sorted(v.M3_TASK_IDS)],
                    supporting_prerequisites=[integration('KL-074')],
                    m2_prerequisite=self.evidence('docs/exec-plans/milestones/M2.json', self.evaluated),
                    exit_checks=exits, integrated_regression=self.evidence(self.regression_path, self.evaluated),
                    boundary_layers=rows, interleaving_layers=interleavings,
                    historical_model_evidence=dict(status='UNVERIFIED_HISTORICAL_DECLARATION',
                                                   independently_reproducible_protocol_model=False),
                    product_requirement_pass_claims=[], production_auto_activation=False,
                    shadow_executable=False, shadow_usability_status='NOT_RUN', r04_e2e_status='NOT_RUN')

    def errors(self, closure):
        return v.m3_milestone_closure_errors(self.root, closure, *SCHEMAS, self.backlog, self.tasks)


@pytest.fixture(scope='module')
def history(tmp_path_factory):
    return History(tmp_path_factory.mktemp('hg044') / 'repo')


def test_prospective_full_git_chain_validates_without_actual_closure(history):
    assert not v.revision_regular_file(ROOT, 'docs/exec-plans/milestones/M3.json',
                                       '9268fc8dd8c071c02dc5c698274dbf6fcd112776')
    assert history.errors(history.closure) == []


@pytest.mark.parametrize('mutation', ['wrong', 'missing', 'extra', 'duplicate', 'namespace', 'kl074'])
def test_exact_task_set_rejects_substitution(history, mutation):
    closure = copy.deepcopy(history.closure)
    rows = closure['integrations']
    if mutation == 'missing':
        rows.pop()
    elif mutation == 'extra':
        rows.append(copy.deepcopy(closure['supporting_prerequisites'][0]))
    elif mutation == 'duplicate':
        rows[-1] = copy.deepcopy(rows[0])
    elif mutation == 'namespace':
        rows[0]['task_identity'] = 'historical/KL-019'
    else:
        rows[0]['display_task_id'] = 'KL-074' if mutation == 'kl074' else 'KL-001'
    assert history.errors(closure)


@pytest.mark.parametrize('mutation', ['missing', 'wrong', 'hash', 'revision'])
def test_m2_prerequisite_binding(history, mutation):
    closure = copy.deepcopy(history.closure)
    if mutation == 'missing':
        closure.pop('m2_prerequisite')
    elif mutation == 'wrong':
        closure['m2_prerequisite']['path'] = 'docs/exec-plans/milestones/M1.json'
    elif mutation == 'hash':
        closure['m2_prerequisite']['sha256'] = '0' * 64
    else:
        closure['m2_prerequisite']['revision'] = history.tested
    assert history.errors(closure)


@pytest.mark.parametrize('field,value', [
    ('production_auto_activation', True), ('shadow_executable', True),
    ('shadow_usability_status', 'PASS'), ('r04_e2e_status', 'PASS'),
    ('product_requirement_pass_claims', ['B04@DC']),
    ('historical_model_evidence', {'status': 'PASS', 'independently_reproducible_protocol_model': True}),
])
def test_schema_rejects_frozen_production_shadow_product_overclaims(history, field, value):
    closure = copy.deepcopy(history.closure)
    closure[field] = value
    assert list(SCHEMAS[0].iter_errors(closure))


@pytest.mark.parametrize('mutation', ['omit', 'promote', 'relabel', 'b04', 'i04', 'equality'])
def test_deferred_layers_cannot_disappear_or_be_promoted(history, mutation):
    closure = copy.deepcopy(history.closure)
    if mutation == 'omit':
        closure['boundary_layers'].pop()
    elif mutation == 'promote':
        next(r for r in closure['boundary_layers'] if r['layer'] == 'E2E')['status'] = 'PASS'
    elif mutation == 'relabel':
        closure['boundary_layers'][1]['layer'] = 'WF'
    elif mutation == 'b04':
        next(r for r in closure['boundary_layers'] if r['requirement_id'] == 'B04')['status'] = 'PASS'
    elif mutation == 'i04':
        closure['interleaving_layers'][-1]['status'] = 'PASS'
    else:
        closure['interleaving_layers'][0]['layer'] = 'PU'
    assert v.m3_layer_errors(history.root, closure, history.evaluated)


@pytest.mark.parametrize('field', ['task_identity', 'check_id', 'tested_commit', 'command', 'oracle_sha256', 'raw', 'result_artifact'])
def test_named_task_witness_must_bind_result_oracle_and_regular_blob(history, field):
    witness = copy.deepcopy(history.closure['exit_checks'][0]['task_checks'][0])
    name, check = witness['task_identity'].split('/')[-1], witness['check_id']
    if field in ('raw', 'result_artifact'):
        witness[field]['sha256'] = '0' * 64
    else:
        witness[field] = '0' * 40 if field == 'tested_commit' else 'wrong'
    assert v.m3_task_check_errors(history.root, witness, name, check, history.tasks[name], history.records[name], history.evaluated)


@pytest.mark.parametrize('mutation', ['failed', 'zero', 'skipped', 'wrong-selector', 'wrong-command', 'stale', 'missing028', 'missing029', 'hash', 'type', 'provenance', 'duplicate-json', 'collection-type'])
def test_integrated_regression_fails_closed(history, mutation):
    payload = copy.deepcopy(history.payload)
    records = copy.deepcopy(history.records)
    run = payload['executions'][3]
    if mutation == 'failed':
        run['exit_code'] = 1
    elif mutation == 'zero':
        payload['executions'] = []
    elif mutation == 'wrong-command':
        run['command'] = 'uv run pytest -q arbitrary.py'
    elif mutation == 'stale':
        payload['tested_commit'] = history.records['KL-027']['reviewed_head_sha']
    elif mutation in ('missing028', 'missing029'):
        records.pop('KL-028' if mutation == 'missing028' else 'KL-029')
    elif mutation == 'hash':
        run['stdout']['sha256'] = '0' * 64
    elif mutation == 'provenance':
        run['stdout'] = {'path': 'docs/exec-plans/evidence/KL-028/b01_pu.log', 'sha256': '0' * 64}
    elif mutation == 'type':
        run['exit_code'] = False
    else:
        # Append new corrupt raw blobs so freshness passes and the content oracle rejects.
        original = (history.root / run['junit' if mutation == 'skipped' else 'collection']['path']).read_text()
        if mutation == 'collection-type':
            collection = json.loads(original)
            collection['exit_code'] = False
            run['collection'] = history.raw('negative-collection-type.json', json.dumps(collection))
        elif mutation == 'duplicate-json':
            original = (history.root / run['collection']['path']).read_text()
            run['collection'] = history.raw('negative-duplicate.json', original[:-1] + ', "exit_code": 0}')
        elif mutation == 'skipped':
            run['junit'] = history.raw('negative-skipped.xml', original.replace('/>', '><skipped/></testcase>'))
        else:
            collection = json.loads(original)
            collection['nodeids'] = ['tests/unit/foreign.py::test_foreign']
            collection['stdout'] = history.raw('negative-selector-collect.log',
                                              collection['nodeids'][0] + '\n1 test collected in 0.1s\n')
            run['collection'] = history.raw('negative-selector.json', json.dumps(collection))
        revision = history.commit('negative appended raw oracle mutation')
        errors = v.m3_execution_evidence_errors(history.root, payload, revision, revision, records)
        assert errors
        assert not any('stale-or-unintegrated-revision' in e for e in errors)
        expected_error = ('collection-binding' if mutation == 'collection-type' else
                          'duplicate-key' if mutation == 'duplicate-json' else
                          'failed-skipped' if mutation == 'skipped' else 'wrong-selector')
        assert any(expected_error in e for e in errors)
        return
    assert v.m3_execution_evidence_errors(history.root, payload, history.evaluated, history.evaluated, records)


def test_legacy_m1_m2_schema_and_validator_behavior_unchanged():
    b = json.loads((ROOT / v.BACKLOG).read_text())
    tasks = {t['id']: t for t in b['tasks']}
    m1 = json.loads((ROOT / 'docs/exec-plans/milestones/M1.json').read_text())
    m2 = json.loads((ROOT / 'docs/exec-plans/milestones/M2.json').read_text())
    assert v.milestone_closure_errors(ROOT, m1, *SCHEMAS, b, tasks) == []
    assert v.m2_milestone_closure_errors(ROOT, m2, *SCHEMAS, b, tasks) == []


@pytest.mark.parametrize('mutation', ['unmerged', 'missing-review', 'stale-review', 'result-type', 'result-hash', 'reverse-ancestry'])
def test_integrated_chain_rejects_bad_result_review_and_ancestry(history, mutation):
    record = copy.deepcopy(history.records['KL-028'])
    if mutation == 'unmerged':
        record['integration_status'] = 'UNMERGED'
    elif mutation == 'missing-review':
        record['review_record_commit'] = record['reviewed_head_sha']
    elif mutation == 'stale-review':
        record['reviewed_head_sha'] = history.records['KL-029']['reviewed_head_sha']
    elif mutation == 'reverse-ancestry':
        record['result_commit'] = history.evaluated
    else:
        # A new reviewed revision cannot reuse stale required reviews or result bytes.
        path = v.result_paths('KL-028')[0]
        original = (history.root / path).read_text()
        if mutation == 'result-type':
            (history.root / path).unlink()
            (history.root / path).symlink_to('../evidence/KL-028/b01_pu.log')
        else:
            payload = json.loads(original)
            payload['commands_run'][0]['result'] = 'FAIL'
            history.put(path, json.dumps(payload))
        record['result_commit'] = history.commit('negative result mutation')
        record['reviewed_head_sha'] = record['result_commit']
        errors = v.integration_record_errors(history.root, Path('KL-028.json'), record,
                                            *SCHEMAS[1:], history.tasks)
        (history.root / path).unlink()
        history.put(path, original)
        history.commit('restore synthetic result')
        assert errors
        return
    assert v.integration_record_errors(history.root, Path('KL-028.json'), record,
                                       *SCHEMAS[1:], history.tasks)


@pytest.mark.parametrize('mode', ['symlink', 'directory', 'missing', 'traversal', 'revision', 'hash'])
def test_raw_evidence_rejects_git_type_path_revision_hash(history, mode):
    path = history.prefix + 'negative-blob'
    if mode == 'symlink':
        target = history.root / path
        target.symlink_to('0.log')
    elif mode == 'directory':
        history.put(path + '/child', '1 passed in 0.1s\n')
    else:
        history.put(path, '1 passed in 0.1s\n')
    revision = history.commit('negative evidence Git type')
    evidence = dict(path=path, revision=revision,
                    sha256=v.blob_sha_at_revision(history.root, path, revision) if mode != 'directory' else '0' * 64)
    if mode == 'missing':
        evidence['path'] += '-absent'
    elif mode == 'traversal':
        evidence['path'] = '../' + path
    elif mode == 'revision':
        evidence['revision'] = '0' * 40
    elif mode == 'hash':
        evidence['sha256'] = '0' * 64
    with pytest.raises(ValueError):
        v.m3_evidence_bytes(history.root, evidence, revision)
    target = history.root / path
    if target.is_dir():
        (target / 'child').unlink()
        target.rmdir()
    else:
        target.unlink()
    history.commit('restore synthetic raw fixture')


@pytest.mark.parametrize('output', ['', '0 passed', '1 skipped', '1 xfailed', '1 passed, 1 skipped',
                                    '1 passed, 1 xpassed', '1 passed, 1 failed', '1 passed, 1 error'])
def test_zero_skip_xfail_failure_cannot_supply_oracle(output):
    with pytest.raises(ValueError):
        v.m3_pytest_count(output)


def test_premature_real_revision_without028029_rejects(history):
    closure = copy.deepcopy(history.closure)
    base = v.resolve(ROOT, '9268fc8dd8c071c02dc5c698274dbf6fcd112776')
    closure['evaluated_commit'] = base
    closure['m2_prerequisite'] = history.evidence('docs/exec-plans/milestones/M2.json', base)
    assert any('KL-028' in e or 'KL-029' in e for e in history.errors(closure))


def test_governance_scope_excludes_peer_and_runtime_and_closure_instance():
    patterns = v.governance_allowed_patterns('HG-044')
    for path in ('docs/exec-plans/milestones/M3.json', 'docs/exec-plans/integrations/KL-028.json',
                 'docs/exec-plans/completed/KL-029_RESULT.yaml', 'docs/exec-plans/active/KL-028.md',
                 v.BACKLOG, v.TRACEABILITY, 'tests/db/test_boundary_acceptance.py',
                 'src/kineticloop/protocol/execution.py', 'FROZEN_BASELINE.json', '.github/workflows/ci.yml'):
        assert not v.matches(path, patterns)


@pytest.mark.parametrize('mutation', ['missing', 'reversed', 'base-after-dependency'])
def test_prerequisite_merge_must_precede_base_and_tested(history, mutation):
    records = copy.deepcopy(history.records)
    tasks = copy.deepcopy(history.tasks)
    assert not v.m3_dependency_order_errors(history.root, records, tasks)
    if mutation == 'missing':
        records.pop('KL-027')
    elif mutation == 'reversed':
        records['KL-027']['merge_commit'] = history.evaluated
    else:
        tasks['KL-028']['depends_on'].append('KL-029')
    errors = v.m3_dependency_order_errors(history.root, records, tasks)
    assert errors
    if mutation == 'reversed':
        assert any('KL-027:KL-028:base_commit' in e for e in errors)
    elif mutation == 'base-after-dependency':
        assert any('KL-029:KL-028:base_commit' in e for e in errors)


def test_frozen_file_tamper_detected_at_git_revision(history):
    path = '05_KineticLoop_Protocol_v1.2_FROZEN.md'
    original = (history.root / path).read_text()
    history.put(path, original + '\nunauthorized fixture change\n')
    revision = history.commit('negative frozen authority mutation')
    assert v.m3_frozen_authority_errors(history.root, revision)
    history.put(path, original)
    history.commit('restore synthetic frozen authority')


def test_existing_schema_branches_preserved():
    original = json.loads(v.git(ROOT, 'show', '9268fc8dd8c071c02dc5c698274dbf6fcd112776:MILESTONE_CLOSURE.schema.json'))
    current = json.loads((ROOT / v.MILESTONE_CLOSURE_SCHEMA).read_text())
    assert current['oneOf'][:2] == original['oneOf']
    for key, value in original['$defs'].items():
        assert current['$defs'][key] == value


def test_ratified_plan_mapping_guard_preserves_addendum():
    text = (ROOT / v.PROJECT_PLAN).read_text()
    assert not v.m3_closure_plan_errors(text)
    assert not v.m3_closure_plan_errors(text + '\nLater governance.\n')
    assert v.m3_closure_plan_errors(text.replace('<!-- HG044 plan end -->', ''))
    before, block = text.split('## M3 exit-evidence mapping — HG044', 1)
    assert v.m3_closure_plan_errors(before + '## M3 exit-evidence mapping — HG044' + block.replace('12 deferred', 'zero deferred'))


@pytest.mark.parametrize('mode', ['valid', 'symlink', 'directory', 'untracked', 'ambient-tamper'])
def test_actual_closure_record_requires_unchanged_regular_head_blob(tmp_path, mode):
    source = History.__new__(History)
    source.root = tmp_path
    source.git('init', '-q')
    path = 'docs/exec-plans/milestones/M3.json'
    source.put('fixture.json', '{}')
    target = source.root / path
    if mode == 'directory':
        source.put(path + '/child', '{}')
    elif mode == 'symlink':
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to('../../../fixture.json')
    else:
        source.put(path, '{}')
    if mode == 'untracked':
        source.git('add', 'fixture.json')
        source.git('commit', '-qm', 'base without closure record')
    else:
        source.commit('synthetic source record')
    if mode == 'ambient-tamper':
        target.write_text('{"tampered": true}')
    errors = v.m3_closure_record_errors(source.root, target)
    assert not errors if mode == 'valid' else errors
