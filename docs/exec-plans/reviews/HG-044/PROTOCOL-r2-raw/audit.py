"""Independent immutable-Git protocol audit; no lifecycle or implementation writes."""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile

import jsonschema
import yaml

ROOT = Path('/Users/davetian/.codex/worktrees/8578/KineticLoop')
REVIEWED = '080f25cf99eebc81701483bb801c5f2860dbd77f'
BASE = '9268fc8dd8c071c02dc5c698274dbf6fcd112776'
TESTED = '4302c0649c9255ac60be87d90853ee0620e9f019'

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)

def blob(path, rev=REVIEWED):
    entry = git('ls-tree', rev, '--', path).decode().split()
    assert entry and entry[0] in ('100644', '100755'), (path, entry)
    return git('show', rev + ':' + path)

def data(path, rev=REVIEWED):
    return json.loads(blob(path, rev))

def digest(content):
    return hashlib.sha256(content).hexdigest()

with tempfile.TemporaryDirectory(prefix='hg044-protocol-r2-') as scratch:
    source = Path(scratch) / 'validator.py'
    source.write_bytes(blob('tools/harness/validate_harness.py'))
    spec = importlib.util.spec_from_file_location('protocol_review_validator', source)
    v = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(v)
    backlog = data(v.BACKLOG)
    tasks = {t['id']: t for t in backlog['tasks']}
    expected = {f'KL-{i:03d}' for i in range(19, 30)} | {f'KL-{i:03d}' for i in range(75, 80)}
    active = {t['id'] for t in tasks.values() if t['milestone'] == 'M3' and t['status'] != 'SUPERSEDED'}
    assert active == expected == v.M3_TASK_IDS and len(active) == 16
    assert tasks['KL-074']['milestone'] == 'M1'
    assert 'KL-078' in tasks['KL-076']['depends_on'] and 'KL-079' in tasks['KL-077']['depends_on']
    schemas = [jsonschema.Draft202012Validator(data(p)) for p in (
        v.MILESTONE_CLOSURE_SCHEMA, v.INTEGRATION_SCHEMA, 'THREAD_RESULT.schema.json', 'THREAD_REVIEW.schema.json')]
    assert not v.milestone_closure_errors(ROOT, data('docs/exec-plans/milestones/M1.json'), *schemas, backlog, tasks)
    assert not v.m2_milestone_closure_errors(ROOT, data('docs/exec-plans/milestones/M2.json'), *schemas, backlog, tasks)
    pending = list(expected | {'KL-074'})
    records = {}
    missing = []
    while pending:
        name = pending.pop()
        if name in records or name in missing:
            continue
        path = f'docs/exec-plans/integrations/{name}.json'
        if not git('ls-tree', REVIEWED, '--', path):
            missing.append(name)
            pending.extend(tasks[name]['depends_on'])
            continue
        record = data(path)
        records[name] = record
        assert not v.integration_record_errors(ROOT, Path(path), record, *schemas[1:], tasks), name
        for key in ('result_commit', 'reviewed_head_sha', 'review_record_commit', 'merge_commit'):
            assert v.is_ancestor(ROOT, record[key], REVIEWED), (name, key)
        for source_path in v.result_paths_at_revision(ROOT, name, record['result_commit']):
            blob(source_path, record['result_commit'])
        pending.extend(tasks[name]['depends_on'])
    assert sorted(missing) == ['KL-028', 'KL-029']
    for name, record in records.items():
        result_path = v.result_paths_at_revision(ROOT, name, record['reviewed_head_sha'])[0]
        result = v.load_artifact_at_revision(ROOT, result_path, record['reviewed_head_sha'])
        for dep in tasks[name]['depends_on']:
            assert dep in records, (name, dep)
            for key in ('base_commit', 'tested_commit'):
                assert v.is_ancestor(ROOT, records[dep]['merge_commit'], result[key]), (name, dep, key)
    contracts = {}
    for exit_id, mapping in v.M3_EXIT_TASK_CHECKS.items():
        for name, ids in mapping.items():
            for check_id in ids:
                candidates = [c for c in tasks[name]['check_contracts'] if c['check_id'] == check_id]
                assert len(candidates) == 1
                contract = candidates[0]
                key = name + ':' + check_id
                assert v.canonical_value_sha(contract) == v.M3_CHECK_CONTRACT_DIGESTS[key]
                contracts[key] = {'command': contract['command'], 'oracle_sha256': v.canonical_value_sha(contract['pass_oracle'])}
    assert len(contracts) == 52
    ledger = v.packet_json_section(blob('docs/exec-plans/active/KL-028.md').decode(), 'Boundary layer ledger')
    requirements = data('KineticLoop_Acceptance_Spec_v1.2.2.json')['supplemental_boundary_requirements']
    assert not v.m3_boundary_layer_errors(ledger, requirements)
    assert len(ledger) == 31
    deferred = [r for r in ledger if r['disposition'] != 'KL028_PLANNED_EXECUTABLE']
    assert len(deferred) == 12 and all(r['status'] == 'NOT_RUN' for r in deferred)
    assert len([r for r in deferred if r['layer'] == 'E2E']) == 8
    assert {(r['requirement_id'], r['layer']) for r in deferred} == {
        ('B04', 'DC'), ('B04', 'E2E'), ('B05', 'E2E'), ('B07', 'E2E'), ('B08', 'E2E'),
        ('B10', 'E2E'), ('B11', 'PU'), ('B12', 'PU'), ('B14', 'E2E'), ('B14', 'WF'), ('B16', 'E2E'), ('B18', 'E2E')}
    assert not v.m3_frozen_authority_errors(ROOT, REVIEWED)
    assert blob('FROZEN_BASELINE.json') == blob('FROZEN_BASELINE.json', BASE)
    for entry in data('FROZEN_BASELINE.json')['files']:
        assert digest(blob(entry['path'])) == entry['sha256']
    assert not git('ls-tree', REVIEWED, '--', 'docs/exec-plans/milestones/M3.json')
    changed = git('diff', '--name-only', BASE, REVIEWED).decode().splitlines()
    assert all(v.matches(p, v.governance_allowed_patterns('HG-044')) for p in changed)
    assert not v.governance_suffix_errors(ROOT, TESTED, REVIEWED, 'HG-044', 'tested')
    suffix = git('diff', '--name-only', TESTED, REVIEWED).decode().splitlines()
    assert all(p == 'docs/exec-plans/governance/HG-044.yaml' or p.startswith('docs/exec-plans/evidence/HG-044/') for p in suffix)
    original = data('MILESTONE_CLOSURE.schema.json', BASE)
    current = data('MILESTONE_CLOSURE.schema.json')
    assert current['oneOf'][:2] == original['oneOf']
    assert all(current['$defs'][k] == val for k, val in original['$defs'].items())
    before_ast = ast.parse(blob('tools/harness/validate_harness.py', BASE))
    after_ast = ast.parse(blob('tools/harness/validate_harness.py'))
    before_fns = {n.name: ast.dump(n) for n in before_ast.body if isinstance(n, ast.FunctionDef)}
    after_fns = {n.name: ast.dump(n) for n in after_ast.body if isinstance(n, ast.FunctionDef)}
    changed_fns = [k for k in before_fns if before_fns[k] != after_fns[k]]
    assert set(changed_fns) == {'governance_allowed_patterns', 'validate'}
    captures = []
    governance = yaml.safe_load(blob('docs/exec-plans/governance/HG-044.yaml'))
    for check in governance['checks_run']:
        capture = data(check['evidence_ref'])
        assert capture['command'] == check['command'] and capture['result'] == check['result'] == 'PASS'
        assert capture['tested_commit'] == TESTED and capture['base_commit'] == BASE
        assert type(capture['exit_code']) is int and capture['exit_code'] == 0
        if 'raw_utf8' in capture:
            raw = capture['raw_utf8'].encode()
            assert len(raw) == capture['raw_byte_count'] and digest(raw) == capture['raw_sha256']
        captures.append({'check_id': check['check_id'], 'git_sha256': digest(blob(check['evidence_ref'])), 'raw': capture.get('raw_utf8', '')})
    integrity = data('docs/exec-plans/evidence/HG-044/capture-integrity-4302c06.json')
    for row in integrity['records']:
        capture = data(row['path'])
        assert digest(blob(row['path'])) == row['sha256']
        assert capture['raw_sha256'] == row['raw_sha256'] and capture['raw_byte_count'] == row['raw_byte_count']
    for group in ('documents', 'machine_readable'):
        for entry in data('CURRENT_DOCUMENT_INDEX.json')[group]:
            assert digest(blob(entry['path'])) == entry['sha256']
    report = dict(reviewed_head_sha=REVIEWED, tested_commit=TESTED, protected_base_sha=BASE,
                  active_m3=sorted(active), supporting_prerequisite='KL-074@M1',
                  existing_transitive_integrations=len(records), prospective_missing=sorted(missing),
                  named_check_contracts=contracts, deferred_boundary_layers=deferred,
                  changed_existing_functions=changed_fns, tested_suffix=suffix,
                  captures=captures, status='PASS')
    print(json.dumps(report, indent=2))
