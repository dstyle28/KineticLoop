"""Independent GENERAL audit bound to the exact HG042 reviewed Git tree."""
import ast
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

import jsonschema
import yaml

ROOT = Path.cwd()
BASE = '93b38f20a3f3d71206515fb0f4d852f5b0b6d344'
TESTED = 'e4134f963450db1522fd6c3339e4cb036fcf5ffe'
REVIEWED = '24513e86d90799edb951fa2bdf52ba433c59318a'
def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)
def blob(sha, path):
    return git('show', sha + ':' + path)
def parsed(sha, path):
    return json.loads(blob(sha, path))

assert git('rev-parse', 'HEAD').decode().strip() == REVIEWED
spec = importlib.util.spec_from_file_location('general_validator', ROOT / 'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
old = parsed(BASE, v.BACKLOG)
new = parsed(REVIEWED, v.BACKLOG)
before = {t['id']: t for t in old['tasks']}
tasks = {t['id']: t for t in new['tasks']}
assert list(before) == list(tasks)
assert [n for n in before if before[n] != tasks[n]] == ['KL-028', 'KL-029']
assert {k: x for k, x in old.items() if k != 'tasks'} == {k: x for k, x in new.items() if k != 'tasks'}
changed = git('diff', '--name-only', BASE, REVIEWED).decode().splitlines()
record = yaml.safe_load(blob(REVIEWED, 'docs/exec-plans/governance/HG-042.yaml'))
assert sorted(record['files_changed']) == sorted(changed)
assert record['base_commit'] == BASE and record['tested_commit'] == TESTED
assert record['change_status'] == 'PASS'
assert v.governance_suffix_errors(ROOT, TESTED, REVIEWED, 'HG-042', 'tested') == []
for path in ('05_KineticLoop_Protocol_v1.2_FROZEN.md', '04_KineticLoop_DB_Schema_Design_v0.2_FROZEN.md',
             'FROZEN_BASELINE.json', 'CURRENT_REQUIREMENT_SET.json', 'KineticLoop_Acceptance_Spec_v1.2.2.json',
             'MILESTONE_CLOSURE.schema.json', 'docs/harness/HARNESS_GOVERNANCE_CONTRACT.md',
             'docs/harness/THREAD_REVIEW_CONTRACT.md', '.github/workflows/ci.yml'):
    assert blob(BASE, path) == blob(REVIEWED, path), path
assert not any(p.startswith(('src/', 'migrations/', '.github/', 'docs/exec-plans/completed/', 'docs/exec-plans/milestones/')) for p in changed)
assert not any(p.startswith('docs/exec-plans/reviews/KL-') for p in changed)
old_source = blob(BASE, 'tools/harness/validate_harness.py').decode()
new_source = blob(REVIEWED, 'tools/harness/validate_harness.py').decode()
def functions(source):
    return {n.name: ast.get_source_segment(source, n) for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)}
old_funcs, new_funcs = functions(old_source), functions(new_source)
modified_functions = [n for n in old_funcs if old_funcs[n] != new_funcs[n]]
assert set(modified_functions) == {'packet_errors', 'task_definition_errors'}
for n in ('integration_record_errors', 'review_evidence_exists', 'revision_regular_file', 'revision_git_entry', 'suffix_errors', 'governance_suffix_errors'):
    assert old_funcs[n] == new_funcs[n], n
for path in (v.INDEX, v.MANIFEST):
    a, b = parsed(BASE, path), parsed(REVIEWED, path)
    def without_derived(value):
        if isinstance(value, dict):
            return {k: without_derived(x) for k, x in value.items() if k not in ('sha256', 'bytes')}
        if isinstance(value, list):
            return [without_derived(x) for x in value]
        return value
    assert without_derived(a) == without_derived(b)
boundary, shadow = tasks['KL-028'], tasks['KL-029']
assert not set(boundary['write_paths']) & set(shadow['write_paths'])
assert not set(boundary['resource_keys']) & set(shadow['resource_keys'])
for task in (boundary, shadow):
    assert task['status'] == 'NOT_STARTED' and task['evidence_refs'] == []
    assert task['shared_hotspot'] is False and task['parallel_write_policy'] == 'PARALLEL_IF_DEPENDENCIES_MET'
    assert len(task['write_paths']) == 3
    assert task['requirements_covered'] == before[task['id']]['requirements_covered']
    assert set(before[task['id']]['review_requirements']) <= set(task['review_requirements'])
    text = blob(REVIEWED, 'docs/exec-plans/active/' + task['id'] + '.md').decode()
    assert v.packet_json_section(text, 'Prospective check status') == {n: 'NOT_RUN' for n in task['checks_required_for_this_task']}
    for pattern in ('RESULT',):
        assert not any(git('ls-tree', REVIEWED, '--', p) for p in v.result_paths(task['id']))
ledger = v.packet_json_section(blob(REVIEWED, 'docs/exec-plans/active/KL-028.md').decode(), 'Boundary layer ledger')
assert len(ledger) == 31 and all(r['status'] == 'NOT_RUN' for r in ledger)
executable = [r for r in ledger if r['disposition'] == 'KL028_PLANNED_EXECUTABLE']
assert len(executable) == 19
assert {layer: sum(r['layer'] == layer for r in executable) for layer in ('PU', 'DC')} == {'PU': 6, 'DC': 13}
assert len([r for r in ledger if r['disposition'] != 'KL028_PLANNED_EXECUTABLE']) == 12
schemas = [jsonschema.Draft202012Validator(parsed(REVIEWED, p)) for p in ('INTEGRATION_RECORD.schema.json', 'THREAD_RESULT.schema.json', 'THREAD_REVIEW.schema.json')]
integrations = {}
for n in ('KL-075', 'KL-076', 'KL-077', 'KL-079', 'KL-027'):
    path = f'docs/exec-plans/integrations/{n}.json'
    item = parsed(REVIEWED, path)
    assert v.integration_record_errors(ROOT, Path(path), item, *schemas, tasks) == []
    merged, reviewed, review_commit = item['merge_commit'], item['reviewed_head_sha'], item['review_record_commit']
    assert v.is_ancestor(ROOT, merged, BASE)
    parents = git('rev-list', '--parents', '-n', '1', merged).decode().split()[1:]
    assert len(parents) == 2 and parents[1] == review_commit
    assert v.suffix_errors(ROOT, reviewed, review_commit, n, 'review') == []
    result_paths = v.result_paths_at_revision(ROOT, n, item['result_commit'])
    assert len(result_paths) == 1
    raw = blob(item['result_commit'], result_paths[0])
    assert raw == blob(reviewed, result_paths[0]) == blob(BASE, result_paths[0]) == blob(REVIEWED, result_paths[0])
    assert yaml.safe_load(raw)['integration_status'] == 'UNMERGED'
    refs = []
    for kind in tasks[n]['review_requirements']:
        review_path = f'docs/exec-plans/reviews/{n}/{kind}.json'
        assert blob(BASE, review_path) == blob(REVIEWED, review_path)
        review = parsed(review_commit, review_path)
        assert review['status'] == 'PASS' and review['reviewed_head_sha'] == reviewed
        for ref in review.get('evidence_refs', []):
            at_reviewed = v.revision_regular_file(ROOT, ref, reviewed)
            source = reviewed if at_reviewed else review_commit
            if not at_reviewed:
                assert ref.startswith(f'docs/exec-plans/reviews/{n}/')
                assert v.revision_git_entry(ROOT, ref, reviewed) is None
            entry = v.revision_git_entry(ROOT, ref, source)
            assert entry and entry[0] in (b'100644', b'100755') and entry[1] == b'blob'
            assert git('cat-file', '-t', entry[2].decode()).strip() == b'blob'
            refs.append({'review_type': kind, 'path': ref, 'source_sha': source, 'blob_oid': entry[2].decode()})
    integrations[n] = {'merge_commit': merged, 'normal_merge_parents': parents, 'result_sha256': hashlib.sha256(raw).hexdigest(), 'refs': refs}
checks = []
assert len(record['checks_run']) == 9
for check in record['checks_run']:
    raw = parsed(REVIEWED, check['evidence_ref'])
    data = raw['raw_utf8'].encode()
    assert raw['tested_commit'] == TESTED and raw['base_commit'] == BASE
    assert raw['check_id'] == check['check_id'] and raw['command'] == check['command']
    assert raw['exit_code'] == 0 and raw['result'] == check['result'] == 'PASS'
    assert hashlib.sha256(data).hexdigest() == raw['raw_sha256'] and len(data) == raw['raw_byte_count']
    checks.append({'check_id': check['check_id'], 'tested_commit': TESTED, 'raw_sha256': raw['raw_sha256'], 'raw_bytes': len(data)})
print(json.dumps({'reviewed_head_sha': REVIEWED, 'protected_base': BASE, 'tested_commit': TESTED,
                  'changed_task_definitions': ['KL-028', 'KL-029'], 'modified_existing_validator_functions': modified_functions,
                  'frozen_source_ci_completed_history_unchanged': True, 'hg043_provenance_functions_byte_identical': True,
                  'ledger': {'total': 31, 'executable': 19, 'deferred': 12, 'all_statuses': 'NOT_RUN'},
                  'final_raw_checks': checks, 'integration_provenance': integrations}, indent=2))
