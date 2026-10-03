'''Independent exact-revision DB concurrency governance review audit.'''
from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
BASE = '95ddd75d3eb410b7dffa15a1017276c504adc9a6'
TESTED = '4db695230c2158f67394c8ac79a5f0fdf511849a'
REVIEWED = 'ceed78db431a348aae0b599a5e1b09bb082fb968'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def data(path, revision=REVIEWED):
    return git('show', revision + ':' + path)


def obj(path, revision=REVIEWED):
    return json.loads(data(path, revision))


def module(name, path):
    assert (ROOT / path).read_bytes() == data(path)
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def constants(source):
    names = {'M3_TASK_IDS', 'M3_EXIT_TASK_CHECKS', 'M3_CHECK_CONTRACT_DIGESTS',
             'M3_REGRESSION_COMMANDS', 'SOURCE_DECISION_PLAN_SHA256',
             'SOURCE_FIXTURE_REPLACEMENTS'}
    nodes = []
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(
            (isinstance(t, ast.Name) and t.id in names) or
            (isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name)
             and t.value.id in names) for t in node.targets):
            nodes.append(node)
        elif (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
              and isinstance(node.value.func, ast.Attribute)
              and isinstance(node.value.func.value, ast.Name)
              and node.value.func.value.id in names):
            nodes.append(node)
    result = {}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<revision-constants>', 'exec'), result)
    return {name: result[name] for name in names}


def main():
    assert git('rev-parse', 'HEAD').decode().strip() == REVIEWED
    for left, right in [(BASE, TESTED), (TESTED, REVIEWED)]:
        git('merge-base', '--is-ancestor', left, right)
    v = module('db_review_validator', 'tools/harness/validate_harness.py')
    c = module('db_review_compact', 'tools/harness/compact_evidence.py')
    import yaml
    record = yaml.safe_load(data('docs/exec-plans/governance/HG-049.yaml'))
    assert record['base_commit'] == BASE and record['tested_commit'] == TESTED
    assert record['change_status'] == 'PASS' and record['frozen_impact'] == 'NONE'
    changed = set(git('diff', '--name-only', BASE, REVIEWED).decode().splitlines())
    assert set(record['files_changed']) == changed
    assert all(v.matches(p, v.governance_allowed_patterns('HG-049')) for p in changed)
    assert not any(p.startswith(('src/', 'tests/db/', '.github/', 'docs/history/',
                                 'docs/exec-plans/completed/', 'docs/exec-plans/integrations/',
                                 'docs/exec-plans/milestones/')) for p in changed)
    for p in ['FROZEN_BASELINE.json', 'CURRENT_REQUIREMENT_SET.json',
              '06_KineticLoop_Project_Plan_v0.6_HARNESS_HARDENED.md',
              'docs/harness/M3_CLOSURE_CONTRACT.md', 'pyproject.toml', 'uv.lock']:
        assert data(p, BASE) == data(p)
    assert not v.governance_suffix_errors(ROOT, TESTED, REVIEWED, 'HG-049', 'tested')
    audit = c.audit(ROOT, BASE, REVIEWED, 'HG-049')
    assert not audit['errors']
    before = obj(v.BACKLOG, BASE)
    after = obj(v.BACKLOG)
    old = next(t for t in before['tasks'] if t['id'] == 'KL-080')
    new = next(t for t in after['tasks'] if t['id'] == 'KL-080')
    expected = copy.deepcopy(before)
    selected = next(t for t in expected['tasks'] if t['id'] == 'KL-080')
    selected['deliverables'][1] = new['deliverables'][1]
    selected['check_contracts'][7]['pass_oracle'] = new['check_contracts'][7]['pass_oracle']
    assert expected == after
    assert new['status'] == 'NOT_STARTED' and new['requirements_covered'] == []
    assert len(new['write_paths']) == 19 and len(new['resource_keys']) == 8
    assert len(new['depends_on']) == 10 and len(new['check_contracts']) == 17
    assert len(new['review_requirements']) == 4 and new['evidence_refs'] == []
    old_constants = constants(data('tools/harness/validate_harness.py', BASE))
    new_constants = constants(data('tools/harness/validate_harness.py'))
    key = 'KL-080:source_owner_trajectories_dc'
    old_constants['M3_CHECK_CONTRACT_DIGESTS'][key] = v.canonical_value_sha(new['check_contracts'][7])
    assert old_constants == new_constants
    prior = obj(v.TRACEABILITY, BASE)
    i = next(i for i, t in enumerate(prior['tasks']) if t['id'] == 'KL-080')
    prior['tasks'][i] = v.traceability_projection(new)
    assert prior == obj(v.TRACEABILITY)
    history = [p for p in git('ls-tree', '-r', '--name-only', BASE).decode().splitlines()
               if p.startswith(('docs/history/', 'docs/exec-plans/completed/',
                                'docs/exec-plans/reviews/', 'docs/exec-plans/evidence/',
                                'docs/exec-plans/integrations/', 'docs/exec-plans/milestones/'))]
    assert not changed.intersection(history)
    prerequisites = []
    for task in new['depends_on']:
        integration = obj('docs/exec-plans/integrations/' + task + '.json')
        assert integration['integration_status'] == 'MERGED'
        git('merge-base', '--is-ancestor', integration['merge_commit'], BASE)
        p = 'docs/exec-plans/completed/' + task + '_RESULT.yaml'
        result = yaml.safe_load(data(p))
        assert result['task_status'] == 'PASS'
        prerequisites.append({'identity': result['task_identity'],
                              'merge_commit': integration['merge_commit']})
    assert obj('docs/exec-plans/milestones/M2.json')['closure_status'] == 'PASS'
    sources = ['src/kineticloop/persistence/deterministic_planning.py',
               'src/kineticloop/persistence/transactions.py',
               'src/kineticloop/persistence/protocol_execution.py',
               'src/kineticloop/contracts/commands.py',
               'docs/contracts/deterministic_planning.md',
               'docs/contracts/full_action_preparation.md',
               'docs/contracts/full_test_execution.md',
               'docs/contracts/protocol_execution.md',
               '04_KineticLoop_DB_Schema_Design_v0.2_FROZEN.md',
               '05_KineticLoop_Protocol_v1.2_FROZEN.md']
    hashes = {}
    for p in sources:
        assert data(p, BASE) == data(p)
        hashes[p] = hashlib.sha256(data(p)).hexdigest()
    producer = data(sources[0]).decode()
    tx = data(sources[1]).decode()
    adapter = data(sources[2]).decode()
    assert 'ref_s34_id=UUID(request.sources["nutrition"]["id"])' in producer
    assert 'ref_s34_id=UUID(payload["fitness_id"])' in producer
    assert 'values["demand_feature_id"] = UUID(payload["demand_id"])' in producer
    assert '(demand_basis[2] != demand_basis[3] and not self._coordination_context.get("full_execution_members"))' in tx
    assert 'demand_basis[1] != demand_basis[5]' in tx
    assert tx.index('self.prepare_authorization_basis(**authorization_basis)') < tx.index('self.require_execution_request(execution_request)')
    assert 'full persisted policy requires full execution request; legacy downgrade denied' in tx
    assert 'certificate != expected_certificate' in tx
    assert 'first-use row requires complete owner outcome and bookkeeping' in tx
    assert adapter.index('tx.require_current_fence(') < adapter.index('tx.lock_daily_head(inputs[0], create_first=True)')
    prefix = 'docs/exec-plans/evidence/HG-049/checks-4db6952/'
    check_summaries = []
    for check in record['checks_run']:
        raw = c.read(ROOT, check['evidence_ref'], REVIEWED, tested=TESTED,
                     command=check['command'], exit_code=0)
        assert check['result'] == 'PASS'
        check_summaries.append({'check_id': check['check_id'], 'bytes': len(raw),
                                'stdout_sha256': hashlib.sha256(raw).hexdigest()})
    manifest = json.loads(c.read(ROOT, prefix + 'harness-manifest-json.json', REVIEWED))
    assert manifest['tested_commit'] == TESTED and manifest['dirty_source'] is False
    assert manifest['execution_complete'] is True and manifest['errors'] == []
    collection = json.loads(c.read(ROOT, prefix + 'harness-collection-json.json', REVIEWED))
    observer = json.loads(c.read(ROOT, prefix + 'harness-execution-json.json', REVIEWED))
    ids = collection['collections']['serial']
    assert len(ids) == len(set(ids)) == 1347
    assert set(observer['started']) == set(ids) and len(observer['started']) == len(ids)
    assert collection['exit_code'] == observer['exit_code'] == 0
    assert collection['errors'] == observer['errors'] == []
    for worker_ids in observer['collections'].values():
        assert worker_ids == ids
    assert len(observer['reports']) == 3 * len(ids)
    assert all(r['outcome'] == 'passed' for r in observer['reports'])
    phases = {(r['nodeid'], r['phase']) for r in observer['reports']}
    assert len(phases) == len(observer['reports'])
    assert all((node, phase) in phases for node in ids for phase in ['setup', 'call', 'teardown'])
    counts = {}
    for name, expected_count in [('harness-junit-xml', 1347), ('unit-junit', 241)]:
        xml = ET.fromstring(c.read(ROOT, prefix + name + '.json', REVIEWED))
        cases = list(xml.iter('testcase'))
        assert len(cases) == expected_count
        assert not any(child.tag in {'failure', 'error', 'skipped'} for case in cases for child in case)
        counts[name] = len(cases)
    assert sum('tests/harness/test_source_decision_scope.py::' in node for node in ids) == 59
    assert sum('tests/harness/test_m3_milestone_closure.py::' in node for node in ids) > 0
    self_path = Path(__file__).resolve()
    print(json.dumps({'status': 'PASS', 'review_type': 'DB_CONCURRENCY',
                      'base_commit': BASE, 'tested_commit': TESTED,
                      'reviewed_head_sha': REVIEWED,
                      'executed_verifier_sha256': hashlib.sha256(self_path.read_bytes()).hexdigest(),
                      'historical_paths_unchanged': len(history), 'prerequisites': prerequisites,
                      'source_sha256': hashes, 'checks': check_summaries,
                      'junit_counts': counts, 'focused_source_scope_cases': 59,
                      'evidence_budget': audit,
                      'db_guard_observation': 'STATIC_SOURCE_ONLY; no PostgreSQL execution',
                      'actual_expected_mechanical_denial': 'legacy demand/proposal dependency guard before synthetic certificate',
                      'kl080_product_m3_release_status': 'NOT_RUN',
                      'normal_final_head_hosted_app_full_db_gates': 'PENDING_ROOT_COORDINATION'}, indent=2))


if __name__ == '__main__':
    main()
