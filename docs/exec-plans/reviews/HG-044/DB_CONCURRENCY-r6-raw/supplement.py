"""Bounded independent metadata, gate-wiring and negative integration probes."""
import ast
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

ROOT = Path.cwd()
OUT = ROOT / 'docs/exec-plans/reviews/HG-044/DB_CONCURRENCY-r6-raw'
HEAD = 'cf0b99359d04c136d01fd4c5eeec8a23cd0bbc54'
BASE = '2c44f456a0daf8e6933f20fc3eadc7e1869d6fff'
def blob(path, rev=HEAD):
    return subprocess.check_output(['git', 'show', rev + ':' + path])
def obj(path, rev=HEAD):
    return json.loads(blob(path, rev))
def sha(raw):
    return hashlib.sha256(raw).hexdigest()
def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2) + '\n')
s = importlib.util.spec_from_file_location('supplement_v', ROOT / 'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(s)
s.loader.exec_module(v)
hashes = []
index = obj(v.INDEX)
for entry in index['documents'] + index['machine_readable']:
    raw = blob(entry['path'])
    assert sha(raw) == entry['sha256'], entry['path']
    hashes.append(dict(path=entry['path'], sha256=sha(raw), bytes=len(raw)))
for entry in obj(v.MANIFEST)['files']:
    raw = blob(entry['path'])
    assert sha(raw) == entry['sha256'] and len(raw) == entry['bytes'], entry['path']
save('derived-hashes.json', hashes)
source = blob('tools/harness/validate_harness.py').decode()
tree = ast.parse(source)
validate = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'validate')
calls = [n for n in ast.walk(validate) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
         and n.func.id == 'm3_governance_plan_prefix_errors']
assert len(calls) == 1 and [ast.unparse(a) for a in calls[0].args] == ['root', 'governance_base', 'reviewed']
gate_block = next(n for n in ast.walk(validate) if isinstance(n, ast.If) and
                  ast.unparse(n.test) == 'review_only' and 'governance_target = reviewed' in ast.get_source_segment(source,n))
assert 'governance_base = record_base' in ast.get_source_segment(source,gate_block)
assert 'governance_base = base_sha' in ast.get_source_segment(source,gate_block)
assert 'reviewed = resolve(root, args.governance_reviewed_head)' in ast.get_source_segment(source,validate)
tasks = {t['id']:t for t in obj(v.BACKLOG)['tasks']}
commands = []
for name in v.M3_TASK_IDS:
    for check in tasks[name]['check_contracts']:
        command = check['command']
        if command.startswith('uv run pytest -q '):
            selectors = command.removeprefix('uv run pytest -q ').split()
            full_suite = 'uv run pytest -q ' + ' '.join(dict.fromkeys(selector.split('::',1)[0] for selector in selectors))
            aggregate = ('uv run kl test-unit' if all(s.startswith('tests/unit/') for s in selectors)
                         else 'uv run kl test-harness' if all(s.startswith('tests/harness/') for s in selectors)
                         else None)
            assert command in v.M3_REGRESSION_COMMANDS or full_suite in v.M3_REGRESSION_COMMANDS or aggregate in v.M3_REGRESSION_COMMANDS, (name,command)
            commands.append(dict(task=name,check_id=check['check_id'],command=command,
                                  covering_command=command if command in v.M3_REGRESSION_COMMANDS else full_suite if full_suite in v.M3_REGRESSION_COMMANDS else aggregate))
for required in v.M3_EXIT_TASK_CHECKS.values():
    for name, ids in required.items():
        for check_id in ids:
            command = next(c['command'] for c in tasks[name]['check_contracts'] if c['check_id'] == check_id)
            assert command in v.M3_REGRESSION_COMMANDS, (name,check_id,command)
save('regression-coverage.json', commands)
records = {n:obj(f'docs/exec-plans/integrations/{n}.json') for n in v.M3_TASK_IDS
           if v.revision_regular_file(ROOT,f'docs/exec-plans/integrations/{n}.json',HEAD)}
assert set(v.M3_TASK_IDS)-set(records) == {'KL-028','KL-029'}
payload = dict(change_id='HG-999',tested_commit=HEAD,status='PASS', commands=v.M3_REGRESSION_COMMANDS,executions=[])
errors = v.m3_execution_evidence_errors(ROOT,payload,HEAD,HEAD,records)
assert errors and any('KL-028' in e or 'KL-029' in e for e in errors), errors
broad = (OUT / 'broad-whitespace.stdout').read_text()
paths = sorted(set(line.rsplit(':',2)[0] for line in broad.splitlines()
                   if ': trailing whitespace.' in line or ': new blank line at EOF.' in line))
assert paths and all(p.startswith('docs/exec-plans/reviews/HG-044/') for p in paths), paths
save('supplement.json', dict(reviewed_sha=HEAD, metadata_hashes=True, gate_call=['root','governance_base','reviewed'],
     ordinary_and_review_only_bases_verified=True, full_plain_task_pytest_commands_covered=len(commands),
     missing_actual_integrations_negative=errors, raw_whitespace_paths=paths,
     raw_whitespace_exception_confined_to_own_review_records=True))
print('DB_CONCURRENCY bounded supplement PASS')
