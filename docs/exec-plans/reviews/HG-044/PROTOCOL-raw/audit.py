"""Independent HG044 PROTOCOL review: read-only exact-revision checks."""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parent
BASE = '9268fc8dd8c071c02dc5c698274dbf6fcd112776'
TESTED = 'e748b37ec92e119190afad87478b7ecb951e5b5d'
REVIEWED = '351f0eda41ad492e66115f9ea1e41e3e0f9abf3d'

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)

def blob(revision, path):
    return git('show', revision + ':' + path)

def sha(data):
    return hashlib.sha256(data).hexdigest()

spec = importlib.util.spec_from_file_location('review_validator', ROOT / 'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
assert git('rev-parse', 'HEAD').decode().strip() == REVIEWED
report = {'reviewed_head_sha': REVIEWED, 'base_commit': BASE, 'tested_commit': TESTED,
          'checks': {}, 'mapped_checks': [], 'captures': []}
source = blob(REVIEWED, 'tools/harness/validate_harness.py').decode()
prior = blob(BASE, 'tools/harness/validate_harness.py').decode()
def functions(text):
    return {n.name: ast.get_source_segment(text, n) for n in ast.parse(text).body
            if isinstance(n, ast.FunctionDef)}
old, new = functions(prior), functions(source)
preserved = ('milestone_closure_errors', 'm2_milestone_closure_errors',
             'm2_execution_evidence_errors', 'integration_record_errors',
             'review_evidence_exists', 'semantic_result_errors',
             'governance_suffix_errors', 'm3_boundary_layer_errors',
             'm3_boundary_shadow_definition_errors', 'm3_boundary_shadow_packet_errors')
report['preserved_functions'] = {}
for name in preserved:
    assert old[name] == new[name], name
    report['preserved_functions'][name] = sha(new[name].encode())
schema_old = json.loads(blob(BASE, 'MILESTONE_CLOSURE.schema.json'))
schema_new = json.loads(blob(REVIEWED, 'MILESTONE_CLOSURE.schema.json'))
assert schema_old['oneOf'] == schema_new['oneOf'][:2]
assert all(schema_new['$defs'][k] == val for k, val in schema_old['$defs'].items())
report['checks']['m1_m2_schema_and_functions_preserved'] = True
frozen = json.loads(blob(REVIEWED, 'FROZEN_BASELINE.json'))
assert blob(BASE, 'FROZEN_BASELINE.json') == blob(REVIEWED, 'FROZEN_BASELINE.json')
report['frozen_files'] = []
for entry in frozen['files']:
    actual = sha(blob(REVIEWED, entry['path']))
    assert actual == entry['sha256']
    assert blob(BASE, entry['path']) == blob(REVIEWED, entry['path'])
    report['frozen_files'].append({'path': entry['path'], 'sha256': actual})
report['checks']['frozen_authority_unchanged'] = True
plan = '06_KineticLoop_Project_Plan_v0.6_HARNESS_HARDENED.md'
assert blob(REVIEWED, plan).decode().split('## M3 exit-evidence mapping — HG044', 1)[0] == blob(BASE, plan).decode() + '\n'
assert v.m3_closure_plan_errors(blob(REVIEWED, plan).decode()) == []
assert v.governance_suffix_errors(ROOT, TESTED, REVIEWED, 'HG-044', 'tested') == []
changed = git('diff', '--name-only', BASE, REVIEWED).decode().splitlines()
assert all(v.matches(p, v.governance_allowed_patterns('HG-044')) for p in changed)
assert not v.revision_regular_file(ROOT, 'docs/exec-plans/milestones/M3.json', REVIEWED)
report['checks']['scope_plan_prefix_no_closure_and_tested_suffix'] = True
report['changed_paths'] = changed
tasks = {t['id']: t for t in json.loads(blob(REVIEWED, v.BACKLOG))['tasks']}
assert {t['id'] for t in tasks.values() if t['milestone'] == 'M3' and t['status'] != 'SUPERSEDED'} == v.M3_TASK_IDS
for exit_id, mapping in v.M3_EXIT_TASK_CHECKS.items():
    for name, checks in mapping.items():
        task = tasks[name]
        contracts = {c['check_id']: c for c in task['check_contracts']}
        for check in checks:
            contract = contracts[check]
            digest = v.canonical_value_sha(contract)
            assert digest == v.M3_CHECK_CONTRACT_DIGESTS[name + ':' + check]
            assert contract['command'] in v.M3_REGRESSION_COMMANDS
            item = {'exit_id': exit_id, 'task_identity': task['task_identity'],
                    'check_id': check, 'command': contract['command'],
                    'contract_sha256': digest, 'pass_oracle': contract['pass_oracle'],
                    'oracle_sha256': v.canonical_value_sha(contract['pass_oracle'])}
            if name not in ('KL-028', 'KL-029'):
                integration = json.loads(blob(REVIEWED, f'docs/exec-plans/integrations/{name}.json'))
                reviewed = integration['reviewed_head_sha']
                paths = v.result_paths_at_revision(ROOT, name, reviewed)
                assert len(paths) == 1
                result = v.load_artifact_at_revision(ROOT, paths[0], reviewed)
                command = next(c for c in result['commands_run'] if c['check_id'] == check)
                ref = command['evidence_ref']
                witness = {'task_identity': task['task_identity'], 'check_id': check,
                           'command': command['command'], 'result': 'PASS',
                           'tested_commit': result['tested_commit'],
                           'oracle_sha256': item['oracle_sha256'],
                           'result_artifact': {'path': paths[0], 'revision': reviewed,
                                               'sha256': sha(blob(reviewed, paths[0]))},
                           'raw': {'path': ref, 'revision': reviewed, 'sha256': sha(blob(reviewed, ref))}}
                assert v.m3_task_check_errors(ROOT, witness, name, check, task, integration, REVIEWED) == []
                item['verified_integrated_witness'] = witness
            else:
                assert not v.revision_regular_file(ROOT, f'docs/exec-plans/integrations/{name}.json', REVIEWED)
                item['status'] = 'PROSPECTIVE_NOT_RUN'
            report['mapped_checks'].append(item)
rows = v.packet_json_section(blob(REVIEWED, 'docs/exec-plans/active/KL-028.md').decode(), 'Boundary layer ledger')
requirements = json.loads(blob(REVIEWED, 'KineticLoop_Acceptance_Spec_v1.2.2.json'))['supplemental_boundary_requirements']
assert v.m3_boundary_layer_errors(rows, requirements) == []
assert len(rows) == 31
assert sum(r['disposition'] == 'KL028_PLANNED_EXECUTABLE' for r in rows) == 19
assert all(r['status'] == 'NOT_RUN' for r in rows)
report['boundary_rows'] = rows
report['checks']['exact_task_mapping_oracles_and_truthful_31_layer_ledger'] = True
manifest = json.loads(blob(REVIEWED, 'docs/exec-plans/evidence/HG-044/capture-integrity-e748b37.json'))
for entry in manifest['records']:
    data = blob(REVIEWED, entry['path'])
    assert sha(data) == entry['sha256']
    capture = json.loads(data)
    raw = capture['raw_utf8'].encode()
    assert sha(raw) == entry['raw_sha256'] == capture['raw_sha256']
    assert len(raw) == entry['raw_byte_count'] == capture['raw_byte_count']
    assert capture['tested_commit'] == TESTED and capture['base_commit'] == BASE
    assert capture['exit_code'] == 0 and capture['result'] == 'PASS'
    if capture['check_id'] in ('focused', 'harness', 'unit'):
        assert v.m3_pytest_count(raw.decode()) == {'focused':79, 'harness':869, 'unit':232}[capture['check_id']]
    report['captures'].append(capture)
report['checks']['selected_final_capture_hashes_counts_and_revision'] = True
selected = ['zero_skip_xfail_failure', 'governance_scope', 'existing_schema_branches',
            'ratified_plan_mapping', 'actual_closure_record', 'symlink_is_rejected',
            'reader_parses_checked']
command = ['/private/tmp/hg044-venv/bin/python', '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
           '--basetemp=/private/tmp/hg044-protocol-checks', 'tests/harness/test_m3_milestone_closure.py',
           '-k', ' or '.join(selected)]
run = subprocess.run(command, cwd=ROOT, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(ROOT/'src')), capture_output=True)
(OUT / 'targeted-pytest.log').write_bytes(run.stdout + run.stderr)
assert run.returncode == 0
report['review_execution'] = {'command': command, 'exit_code': run.returncode,
                            'reviewed_head_sha': REVIEWED, 'raw_path': str((OUT/'targeted-pytest.log').relative_to(ROOT)),
                            'sha256': sha(run.stdout + run.stderr)}
report['status'] = 'PASS'
(OUT / 'audit.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'status': report['status'], 'checks': report['checks'],
                  'mapped_check_count': len(report['mapped_checks']), 'preserved_functions': list(report['preserved_functions'])}))
