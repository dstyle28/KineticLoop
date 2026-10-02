import ast
import hashlib
import importlib.util
import json
import re
import subprocess
from pathlib import Path
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).parent
BASE = '2c44f456a0daf8e6933f20fc3eadc7e1869d6fff'
HEAD = 'cf0b99359d04c136d01fd4c5eeec8a23cd0bbc54'
TESTED = '06dab6dbb38221e7111c18811cb20b42b8cc2397'
spec = importlib.util.spec_from_file_location('sec_r6_validator', ROOT / 'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
errors = []
def check(condition, name):
    if not condition:
        errors.append(name)
def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)
def bound(path, rev):
    entry = git('ls-tree', rev, '--', path).decode().strip()
    check(bool(entry) and entry.split()[0] in ('100644', '100755') and entry.split()[1] == 'blob', 'regular:' + rev + ':' + path)
    data = git('show', rev + ':' + path)
    return {'path': path, 'revision': rev, 'entry': entry, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}, data
def obj(path, rev):
    meta, data = bound(path, rev)
    return meta, v.load_artifact_text(data.decode(), Path(path).suffix)

check(git('rev-parse', 'HEAD').decode().strip() == HEAD, 'exact-reviewed-head')
changes = git('diff', '--name-only', BASE, HEAD).decode().splitlines()
record_meta, record = obj('docs/exec-plans/governance/HG-044.yaml', HEAD)
check(set(record['files_changed']) == set(changes), 'exact-write-declaration')
check(record['base_commit'] == BASE and record['tested_commit'] == TESTED and record['frozen_impact'] == 'NONE', 'governance-bindings')
inventory = []
secret_hits = []
for path in changes:
    check(v.matches(path, v.governance_allowed_patterns('HG-044')), 'scope:' + path)
    meta, data = bound(path, HEAD)
    inventory.append(meta)
    # Report paths only, never any candidate credential contents.
    if re.search(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{32,}', data):
        secret_hits.append(path)
check(not secret_hits, 'credential-patterns-present')
check('docs/exec-plans/milestones/M3.json' not in changes and not (ROOT / 'docs/exec-plans/milestones/M3.json').exists(), 'no-actual-M3')
suffix_errors = v.governance_suffix_errors(ROOT, TESTED, HEAD, 'HG-044', 'tested')
check(not suffix_errors, 'legal-tested-suffix:' + str(suffix_errors))
check(not v.m3_governance_plan_prefix_errors(ROOT, BASE, HEAD), 'protected-plan-prefix')
index_meta, index = obj('CURRENT_DOCUMENT_INDEX.json', HEAD)
for item in index['documents'] + index['machine_readable']:
    meta, data = bound(item['path'], HEAD)
    check(meta['sha256'] == item['sha256'], 'current-index:' + item['path'])
frozen_meta, frozen = obj('FROZEN_BASELINE.json', HEAD)
check(git('show', BASE + ':FROZEN_BASELINE.json') == git('show', HEAD + ':FROZEN_BASELINE.json'), 'frozen-baseline-bytes')
for item in frozen['files']:
    meta, data = bound(item['path'], HEAD)
    check(meta['sha256'] == item['sha256'] and data == git('show', BASE + ':' + item['path']), 'frozen:' + item['path'])

captures = []
for selected in record['checks_run']:
    meta, capture = obj(selected['evidence_ref'], HEAD)
    if selected['check_id'] == 'scope':
        check(capture['tested_commit'] == TESTED and capture['base_commit'] == BASE and all(capture['checks'].values()), 'selected-scope')
        captures.append(dict(meta, check_id='scope'))
        continue
    raw = capture['raw_utf8'].encode()
    check(capture['command'] == selected['command'], 'selected-command:' + selected['check_id'])
    check(capture['tested_commit'] == TESTED and capture['base_commit'] == BASE, 'selected-revision:' + selected['check_id'])
    check(capture['exit_code'] == 0 and type(capture['exit_code']) is int and capture['result'] == selected['result'] == 'PASS', 'selected-status:' + selected['check_id'])
    check(hashlib.sha256(raw).hexdigest() == capture['raw_sha256'] and len(raw) == capture['raw_byte_count'], 'selected-raw:' + selected['check_id'])
    counts = {'focused': 90, 'harness': 880, 'unit': 241}
    if selected['check_id'] in counts:
        check(v.m3_pytest_count(raw.decode()) == counts[selected['check_id']], 'selected-count:' + selected['check_id'])
    captures.append(dict(meta, check_id=selected['check_id'], raw_sha256=capture['raw_sha256'], raw_bytes=len(raw)))
integrity_meta, integrity = obj('docs/exec-plans/evidence/HG-044/capture-integrity-06dab6d.json', HEAD)
for item in integrity['records']:
    current = next(c for c in captures if c['path'] == item['path'])
    check(current['sha256'] == item['sha256'] and current['raw_sha256'] == item['raw_sha256'] and current['raw_bytes'] == item['raw_byte_count'], 'integrity:' + item['check_id'])
diag_meta, diagnostic = obj('docs/exec-plans/evidence/HG-044/gate-diagnostic-06dab6d.json', HEAD)
check(hashlib.sha256(diagnostic['raw_utf8'].encode()).hexdigest() == diagnostic['raw_sha256'], 'diagnostic-integrity')
check(diagnostic['exit_code'] == 1 and 'TypeError' not in diagnostic['raw_utf8'], 'repaired-diagnostic')
check(all(line == 'HARNESS_CHECK_FAIL' or line == 'git-worktree-not-clean' or line.startswith('governance-review-stale-change:') for line in diagnostic['raw_utf8'].splitlines()), 'diagnostic-only-expected-errors')

backlog = v.load_artifact_at_revision(ROOT, v.BACKLOG, HEAD)
definition_errors, tasks = v.task_definition_errors(ROOT, backlog, HEAD)
check(not definition_errors, 'task-definitions')
schemas = {name: Draft202012Validator(v.load_artifact(ROOT / path)) for name, path in [('integration', v.INTEGRATION_SCHEMA), ('result', 'THREAD_RESULT.schema.json'), ('review', 'THREAD_REVIEW.schema.json')]}
records, chain_inventory = {}, []
pending = list(v.M3_TASK_IDS | {'KL-074'})
absent = []
while pending:
    name = pending.pop()
    if name in records or name in absent:
        continue
    path = f'docs/exec-plans/integrations/{name}.json'
    if not v.revision_regular_file(ROOT, path, HEAD):
        absent.append(name)
        continue
    meta, integration = obj(path, HEAD)
    records[name] = integration
    chain_inventory.append(meta)
    integration_errors = v.integration_record_errors(ROOT, Path(path), integration, schemas['integration'], schemas['result'], schemas['review'], tasks)
    check(not integration_errors, 'integration:' + name + ':' + str(integration_errors))
    for key in ('result_commit', 'reviewed_head_sha', 'review_record_commit', 'merge_commit'):
        check(v.resolve(ROOT, integration[key]) == integration[key] and v.is_ancestor(ROOT, integration[key], HEAD), 'reachable:' + name + ':' + key)
    for revision in (integration['result_commit'], integration['reviewed_head_sha']):
        result_paths = v.result_paths_at_revision(ROOT, name, revision)
        check(len(result_paths) == 1, 'result-count:' + name)
        for result_path in result_paths:
            rmeta, result = obj(result_path, revision)
            chain_inventory.append(rmeta)
            for command in result['commands_run']:
                if command.get('evidence_ref'):
                    chain_inventory.append(bound(command['evidence_ref'], integration['reviewed_head_sha'])[0])
    for kind in tasks[name]['review_requirements']:
        path = f'docs/exec-plans/reviews/{name}/{kind}.json'
        rmeta, review = obj(path, integration['review_record_commit'])
        chain_inventory.append(rmeta)
        for ref in review.get('evidence_refs', []):
            # Mirror contract source selection independently of helper validation.
            present = bool(git('ls-tree', review['reviewed_head_sha'], '--', ref).strip())
            revision = review['reviewed_head_sha'] if present else integration['review_record_commit']
            if not present:
                check(ref.startswith(f'docs/exec-plans/reviews/{name}/'), 'review-own-suffix:' + ref)
                check(not v.suffix_errors(ROOT, review['reviewed_head_sha'], revision, name, 'review'), 'review-linear-suffix:' + name)
            check(v.relative_path(ref), 'review-normalized-path:' + ref)
            chain_inventory.append(bound(ref, revision)[0])
    pending.extend(tasks[name]['depends_on'])
check(set(absent) == {'KL-028', 'KL-029'}, 'prospective-integrations-absent')
available_tasks = {n: dict(tasks[n], depends_on=[d for d in tasks[n]['depends_on'] if d in records]) for n in records}
check(not v.m3_dependency_order_errors(ROOT, records, available_tasks), 'recursive-dependency-order')

before = git('show', BASE + ':tools/harness/validate_harness.py').decode()
after = git('show', HEAD + ':tools/harness/validate_harness.py').decode()
def functions(source):
    lines = source.splitlines(keepends=True)
    return {n.name: ''.join(lines[n.lineno - 1:n.end_lineno]) for n in ast.parse(source).body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
old, new = functions(before), functions(after)
preserved = ['integration_record_errors', 'milestone_closure_errors', 'm2_milestone_closure_errors', 'review_evidence_exists', 'suffix_errors', 'revision_regular_file']
for name in preserved:
    check(old[name] == new[name], 'legacy-preserved:' + name)
result = {'reviewed_head_sha': HEAD, 'base_commit': BASE, 'tested_commit': TESTED, 'errors': errors, 'changed_path_count': len(changes), 'changed_inventory': inventory, 'selected_captures': captures, 'diagnostic': diag_meta, 'recursive_integrations': sorted(records), 'absent_prospective_integrations': sorted(absent), 'chain_inventory': chain_inventory, 'secret_pattern_hit_paths': secret_hits, 'preserved_functions': preserved, 'tested_suffix_errors': suffix_errors}
(OUT / 'audit.json').write_text(json.dumps(result, indent=2) + '\n')
(OUT / 'source-diff.patch').write_bytes(git('diff', BASE, HEAD, '--', 'MILESTONE_CLOSURE.schema.json', 'tools/harness/validate_harness.py', 'tests/harness/test_m3_milestone_closure.py', 'docs/harness/M3_CLOSURE_CONTRACT.md', v.PROJECT_PLAN))
print(json.dumps({'errors': errors, 'paths': len(changes), 'recursive_integrations': len(records), 'chain_bindings': len(chain_inventory), 'captures': len(captures)}))
raise SystemExit(bool(errors))
