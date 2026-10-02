"""Independent HG044 r6 review: bounded Git inventory, authority and capture audit."""
import ast
import hashlib
import importlib.util
import json
import re
import subprocess
from pathlib import Path

import jsonschema

ROOT = Path.cwd()
OUT = ROOT / 'docs/exec-plans/reviews/HG-044/GENERAL-r6-raw'
BASE = '2c44f456a0daf8e6933f20fc3eadc7e1869d6fff'
TESTED = '06dab6dbb38221e7111c18811cb20b42b8cc2397'
REVIEWED = 'cf0b99359d04c136d01fd4c5eeec8a23cd0bbc54'
def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)
def blob(path, revision=REVIEWED):
    return git('show', revision + ':' + path)
def sha(raw):
    return hashlib.sha256(raw).hexdigest()
def write(name, obj):
    (OUT / name).write_text(json.dumps(obj, indent=2) + '\n')
def functions(raw):
    text = raw.decode()
    lines = text.splitlines(keepends=True)
    return {n.name: ''.join(lines[n.lineno-1:n.end_lineno]).encode()
            for n in ast.parse(text).body if isinstance(n, ast.FunctionDef)}

spec = importlib.util.spec_from_file_location('general_r6_validator', ROOT / 'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
record = v.load_artifact_text(blob('docs/exec-plans/governance/HG-044.yaml').decode(), '.yaml')
checks = {}
checks['head_is_reviewed'] = git('rev-parse', 'HEAD').decode().strip() == REVIEWED
checks['governance_schema'] = not list(jsonschema.Draft202012Validator(json.loads(blob('HARNESS_CHANGE.schema.json'))).iter_errors(record))
checks['record_identity_revisions_status'] = (
    record['change_identity'] == 'harness-governance-v0.1/HG-044'
    and record['base_commit'] == BASE and record['tested_commit'] == TESTED
    and record['change_status'] == 'PASS' and record['packets_refined'] == []
    and record['frozen_impact'] == 'NONE')
changed = git('diff', '--name-only', BASE, REVIEWED).decode().splitlines()
entries = {}
for line in git('ls-tree', '-r', '-z', REVIEWED).decode().split('\0'):
    if line:
        meta, path = line.split('\t')
        mode, kind, oid = meta.split()
        entries[path] = (mode, kind, oid)
inventory = []
for path in changed:
    mode, kind, oid = entries[path]
    raw = blob(path)
    inventory.append(dict(path=path, mode=mode, kind=kind, git_oid=oid,
                          sha256=sha(raw), bytes=len(raw),
                          scope_allowed=v.matches(path, v.governance_allowed_patterns('HG-044'))))
write('inventory.json', dict(base=BASE, reviewed=REVIEWED, entries=inventory))
checks['declared_changed_exact'] = set(record['files_changed']) == set(changed)
checks['path_mode_scope'] = all(i['mode'] in ('100644', '100755') and i['kind'] == 'blob' and i['scope_allowed'] for i in inventory)
checks['validator_executable_mode_preserved'] = git('ls-tree', BASE, 'tools/harness/validate_harness.py').decode().startswith('100755 blob ')
checks['tested_ancestry_and_suffix'] = (v.is_ancestor(ROOT, BASE, TESTED)
    and not v.governance_suffix_errors(ROOT, TESTED, REVIEWED, 'HG-044', 'tested'))
checks['no_actual_closure'] = 'docs/exec-plans/milestones/M3.json' not in entries
old, new = functions(blob('tools/harness/validate_harness.py', BASE)), functions(blob('tools/harness/validate_harness.py'))
changed_functions = [name for name in old if old[name] != new[name]]
checks['only_legacy_function_edits_are_dispatch_scope'] = set(changed_functions) == {'validate', 'governance_allowed_patterns'}
write('functions.json', dict(changed_existing=changed_functions,
    added=sorted(set(new)-set(old)),
    unchanged_hashes={n:sha(raw) for n,raw in old.items() if new[n] == raw}))
old_schema = json.loads(blob('MILESTONE_CLOSURE.schema.json', BASE))
schema = json.loads(blob('MILESTONE_CLOSURE.schema.json'))
jsonschema.Draft202012Validator.check_schema(schema)
checks['m1_m2_schema_preserved'] = (schema['oneOf'][:2] == old_schema['oneOf']
    and all(schema['$defs'][k] == value for k,value in old_schema['$defs'].items()))
checks['committed_plan_prefix'] = v.m3_governance_plan_prefix_errors(ROOT, BASE, REVIEWED) == []
checks['ratified_addendum_hash'] = v.m3_closure_plan_errors(blob(v.PROJECT_PLAN).decode()) == []
checks['protected_frozen_unchanged'] = all(blob(e['path'], BASE) == blob(e['path'])
    for e in json.loads(blob('FROZEN_BASELINE.json'))['files']) and blob('FROZEN_BASELINE.json', BASE) == blob('FROZEN_BASELINE.json')
for name in ('CURRENT_DOCUMENT_INDEX.json', 'HARNESS_DOCUMENT_MANIFEST.json'):
    data = json.loads(blob(name))
    items = data.get('documents', []) + data.get('machine_readable', []) + data.get('files', [])
    checks[name + '_hashes'] = all(sha(blob(e['path'])) == e['sha256'] and
        ('bytes' not in e or len(blob(e['path'])) == e['bytes']) for e in items)
backlog = json.loads(blob(v.BACKLOG))
tasks = {t['id']:t for t in backlog['tasks']}
mapping = {}
selectors = set()
for group, mapping_rows in v.M3_EXIT_TASK_CHECKS.items():
    for task_id, ids in mapping_rows.items():
        for check_id in ids:
            contracts = [c for c in tasks[task_id]['check_contracts'] if c['check_id'] == check_id]
            c, = contracts
            key = task_id + ':' + check_id
            mapping[key] = dict(contract_sha256=v.canonical_value_sha(c), command=c['command'])
            assert mapping[key]['contract_sha256'] == v.M3_CHECK_CONTRACT_DIGESTS[key]
            selectors.update(c['command'].removeprefix('uv run pytest -q ').split())
regression_selectors = {s for c in v.M3_REGRESSION_COMMANDS if c.startswith('uv run pytest -q ')
                        for s in c.removeprefix('uv run pytest -q ').split()}
checks['every_mapped_selector_in_regression'] = selectors <= regression_selectors
write('mapping.json', dict(checks=mapping, mapped_selectors=sorted(selectors), regression_commands=v.M3_REGRESSION_COMMANDS))
captures = []
for check in record['checks_run']:
    p = check['evidence_ref']
    data = json.loads(blob(p))
    assert data['tested_commit'] == TESTED and data['base_commit'] == BASE
    assert data['status' if check['check_id'] == 'scope' else 'result'] == 'PASS'
    if check['check_id'] != 'scope':
        raw = data['raw_utf8'].encode()
        assert data['command'] == check['command'] and data['exit_code'] == 0
        assert sha(raw) == data['raw_sha256'] and len(raw) == data['raw_byte_count']
        if check['check_id'] in ('focused', 'harness', 'unit'):
            assert v.m3_pytest_count(raw.decode()) == {'focused':90, 'harness':880, 'unit':241}[check['check_id']]
        captures.append(dict(check_id=check['check_id'], path=p, blob_sha256=sha(blob(p)),
                             raw_sha256=sha(raw), raw_bytes=len(raw), exit_code=data['exit_code']))
    else:
        assert all(data['checks'].values())
        captures.append(dict(check_id='scope', path=p, blob_sha256=sha(blob(p))))
checks['selected_capture_hash_command_revision_counts'] = len(captures) == 8
write('selected-captures.json', captures)
failed = json.loads(blob('docs/exec-plans/evidence/HG-044/hg044-final-gate-ec0713f.json'))
failed_raw = blob('docs/exec-plans/evidence/HG-044/hg044-final-gate-ec0713f.log')
diagnostic = json.loads(blob('docs/exec-plans/evidence/HG-044/gate-diagnostic-06dab6d.json'))
checks['failed_gate_raw_integrity'] = sha(failed_raw) == failed['raw_sha256'] and failed['exit_code'] == 1
checks['repair_diagnostic_raw_integrity'] = sha(diagnostic['raw_utf8'].encode()) == diagnostic['raw_sha256'] and diagnostic['head'] == TESTED
checks['diagnostic_only_expected_errors'] = all(line == 'HARNESS_CHECK_FAIL'
    or line == 'git-worktree-not-clean' or line.startswith('governance-review-stale-change:')
    for line in diagnostic['raw_utf8'].splitlines()) and 'TypeError' not in diagnostic['raw_utf8']
source_paths = [p for p in changed if not p.startswith('docs/exec-plans/evidence/HG-044/')
                and not p.startswith('docs/exec-plans/reviews/HG-044/')
                and p != 'docs/exec-plans/governance/HG-044.yaml']
(OUT/'source-diff.patch').write_bytes(git('diff', '--no-ext-diff', '--unified=3', BASE, REVIEWED, '--', *source_paths))
source = subprocess.run(['git','diff','--check',BASE,REVIEWED,'--','.',
                        ':(exclude)docs/exec-plans/reviews/HG-044/**'], capture_output=True, cwd=ROOT)
checks['source_whitespace_check'] = source.returncode == 0
(OUT/'source-diff-check.stdout').write_bytes(source.stdout)
(OUT/'source-diff-check.stderr').write_bytes(source.stderr)
broad = subprocess.run(['git','diff','--check',BASE,REVIEWED],capture_output=True,cwd=ROOT)
diagnostic_lines = [s for s in broad.stdout.decode().splitlines() if re.match(r'^docs/.*:\d+: (?:trailing whitespace\.|new blank line at EOF\.)$',s)]
checks['broad_whitespace_only_own_review_raw'] = broad.returncode == 2 and bool(diagnostic_lines) and all(
    s.startswith('docs/exec-plans/reviews/HG-044/') and ('diff.patch:' in s or 'diff.stdout' in s or 'targeted-pytest.log:' in s)
    for s in diagnostic_lines)
write('whitespace.json', dict(source_exit=source.returncode,broad_exit=broad.returncode,
    broad_stdout_bytes=len(broad.stdout),broad_stdout_sha256=sha(broad.stdout),
    broad_stderr_sha256=sha(broad.stderr), diagnostic_count=len(diagnostic_lines),
    affected_paths=sorted({s.split(':')[0] for s in diagnostic_lines}), first_diagnostics=diagnostic_lines[:12],
    explanation='Literal raw diff context bytes in historical own-task review logs are preserved; no full recursive recapture.'))
write('audit.json', dict(base=BASE,tested=TESTED,reviewed=REVIEWED,checks=checks,
    changed_path_count=len(inventory),source_paths=source_paths,status='PASS' if all(checks.values()) else 'FAIL'))
print(json.dumps(checks, indent=2))
assert all(checks.values()), [k for k,value in checks.items() if not value]
