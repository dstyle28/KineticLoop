"""Independent exact-revision GENERAL audit; read-only except own review reports."""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import yaml

ROOT = Path.cwd()
OUT = ROOT / 'docs/exec-plans/reviews/HG-044/GENERAL-r5-raw'
BASE = '2c44f456a0daf8e6933f20fc3eadc7e1869d6fff'
REVIEWED = '027bc2368e36e28aa9956489cb57af297882d671'
TESTED = '7206b60aa4f930caf1bac62db0f397978ea0ec34'
def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)
def blob(path, rev=REVIEWED):
    return git('show', rev + ':' + path)
def digest(data):
    return hashlib.sha256(data).hexdigest()
spec = importlib.util.spec_from_file_location('general_m3', ROOT / 'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
checks = {}
changed = git('diff', '--name-only', BASE, REVIEWED).decode().splitlines()
patch = git('diff', '--binary', BASE, REVIEWED)
(OUT / 'complete-diff.patch').write_bytes(patch)
record = yaml.safe_load(blob('docs/exec-plans/governance/HG-044.yaml'))
checks['exact_record_revisions'] = record['base_commit'] == BASE and record['tested_commit'] == TESTED
checks['exact_files_declared'] = set(changed) == set(record['files_changed'])
checks['bounded_scope'] = all(v.matches(p, v.governance_allowed_patterns('HG-044')) for p in changed)
checks['regular_changed_files'] = all(v.revision_regular_file(ROOT, p, REVIEWED) for p in changed)
checks['current_source_matches_reviewed'] = all((ROOT / p).read_bytes() == blob(p) for p in changed if not p.startswith('docs/exec-plans/reviews/'))
checks['no_actual_M3'] = v.revision_git_entry(ROOT, 'docs/exec-plans/milestones/M3.json', REVIEWED) is None
checks['legal_tested_suffix'] = not v.governance_suffix_errors(ROOT, TESTED, REVIEWED, 'HG-044', 'tested')
suffix = []
for commit in git('rev-list', '--reverse', TESTED + '..' + REVIEWED).decode().splitlines():
    suffix.append({'commit': commit, 'parents': git('rev-list', '--parents', '-n', '1', commit).decode().split()[1:], 'paths': git('diff-tree', '--no-commit-id', '--name-only', '-r', commit).decode().splitlines()})
def functions(data):
    text = data.decode(); lines = text.splitlines(keepends=True)
    return {n.name: ''.join(lines[n.lineno-1:n.end_lineno]) for n in ast.parse(text).body if isinstance(n, ast.FunctionDef)}
old, new = functions(blob('tools/harness/validate_harness.py', BASE)), functions(blob('tools/harness/validate_harness.py'))
modified = [n for n in old if old[n] != new.get(n)]
checks['legacy_core_byte_identical'] = all(old[n] == new[n] for n in ('milestone_closure_errors', 'm2_milestone_closure_errors', 'm2_execution_evidence_errors', 'integration_record_errors', 'review_evidence_exists', 'semantic_result_errors', 'governance_suffix_errors'))
old_schema = json.loads(blob('MILESTONE_CLOSURE.schema.json', BASE)); new_schema = json.loads(blob('MILESTONE_CLOSURE.schema.json'))
checks['legacy_schema_semantically_identical'] = old_schema['oneOf'] == new_schema['oneOf'][:2] and all(new_schema['$defs'][k] == val for k, val in old_schema['$defs'].items())
checks['plan_append_only'] = blob(v.PROJECT_PLAN).decode().split('## M3 exit-evidence mapping — HG044')[0] == blob(v.PROJECT_PLAN, BASE).decode() + '\n'
checks['ratified_plan_guard'] = not v.m3_closure_plan_errors(blob(v.PROJECT_PLAN).decode())
checks['frozen_preserved'] = not v.m3_frozen_authority_errors(ROOT, REVIEWED)
captures = []
integrity = json.loads(blob('docs/exec-plans/evidence/HG-044/capture-integrity-7206b60.json'))
by_path = {row['path']: row for row in integrity['records']}
for check in record['checks_run']:
    data = blob(check['evidence_ref']); capture = json.loads(data)
    if check['check_id'] == 'scope':
        valid = capture['status'] == 'PASS' and all(capture['checks'].values()) and capture['base_commit'] == BASE and capture['tested_commit'] == TESTED
    else:
        raw = capture['raw_utf8'].encode(); row = by_path[check['evidence_ref']]
        valid = (capture['command'] == check['command'] and capture['tested_commit'] == TESTED and capture['base_commit'] == BASE and capture['result'] == 'PASS' and type(capture['exit_code']) is int and capture['exit_code'] == 0 and capture['raw_sha256'] == digest(raw) and capture['raw_byte_count'] == len(raw) and row['sha256'] == digest(data) and row['raw_sha256'] == digest(raw) and row['raw_byte_count'] == len(raw))
        (OUT / ('selected-' + check['check_id'] + '.log')).write_bytes(raw)
    captures.append({'check': check['check_id'], 'valid': valid, 'sha256': digest(data)})
checks['selected_capture_integrity'] = all(row['valid'] for row in captures)
contracts = {t['id']: t for t in json.loads(blob(v.BACKLOG))['tasks']}
pins = []
for exit_id, mapping in v.M3_EXIT_TASK_CHECKS.items():
    for task_id, names in mapping.items():
        for name in names:
            c = next(c for c in contracts[task_id]['check_contracts'] if c['check_id'] == name)
            pins.append({'exit': exit_id, 'task': task_id, 'check': name, 'valid': v.canonical_value_sha(c) == v.M3_CHECK_CONTRACT_DIGESTS[task_id + ':' + name]})
checks['all_contract_pins'] = all(p['valid'] for p in pins)
selectors = {s for t in contracts.values() if t['id'] in v.M3_TASK_IDS for c in t.get('check_contracts', []) if c['command'].startswith('uv run pytest -q ') for s in c['command'].removeprefix('uv run pytest -q ').split()}
regression_selectors = {s for c in v.M3_REGRESSION_COMMANDS if c.startswith('uv run pytest -q ') for s in c.removeprefix('uv run pytest -q ').split()}
checks['regression_covers_all_M3_plain_pytest_suites'] = all(s.startswith('tests/unit/') or s.split('::')[0] in regression_selectors for s in selectors)
checks['regression_covers_every_mapped_selector_exactly'] = all(next(c for c in contracts[n]['check_contracts'] if c['check_id'] == check)['command'] in v.M3_REGRESSION_COMMANDS for mapping in v.M3_EXIT_TASK_CHECKS.values() for n, names in mapping.items() for check in names)
checks['exact_M3_membership'] = {t['id'] for t in contracts.values() if t['milestone'] == 'M3' and t['status'] != 'SUPERSEDED'} == v.M3_TASK_IDS
checks['index_hashes_valid'] = all(digest(blob(e['path'])) == e['sha256'] for group in ('documents', 'machine_readable') for e in json.loads(blob(v.INDEX))[group])
source = subprocess.run(['git', 'diff', '--check', BASE, REVIEWED, '--', '.', ':(exclude)docs/exec-plans/reviews/HG-044/**'], capture_output=True, cwd=ROOT)
(OUT / 'source-diff.log').write_bytes(source.stdout + source.stderr)
checks['source_diff_excluding_own_reviews_clean'] = source.returncode == 0
report = {'base': BASE, 'tested': TESTED, 'reviewed': REVIEWED, 'checks': checks, 'modified_existing_functions': modified, 'complete_diff_sha256': digest(patch), 'changed_paths': changed, 'suffix': suffix, 'selected_captures': captures, 'contract_pins': pins}
(OUT / 'audit.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(checks, sort_keys=True))
assert all(checks.values()), checks
