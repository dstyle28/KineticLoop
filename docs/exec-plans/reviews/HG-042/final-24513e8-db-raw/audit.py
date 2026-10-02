"""Read-only exact-revision HG042 DB governance audit; no DB/lifecycle calls."""
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
HERE = Path('docs/exec-plans/reviews/HG-042/final-24513e8-db-raw')


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def blob(path, revision=REVIEWED):
    entry = git('ls-tree', revision, '--', path).decode().strip()
    assert entry.split()[0] in ('100644', '100755'), (revision, path, entry)
    assert entry.split()[1] == 'blob'
    return git('show', revision + ':' + path)


assert git('rev-parse', 'HEAD').decode().strip() == REVIEWED
record = yaml.safe_load(blob('docs/exec-plans/governance/HG-042.yaml'))
assert record['base_commit'] == BASE and record['tested_commit'] == TESTED
changed = git('diff', '--name-only', BASE, REVIEWED).decode().splitlines()
assert changed == sorted(record['files_changed'])
assert not any(p.startswith(('src/', 'migrations/', '.github/', 'docs/exec-plans/completed/'))
               for p in changed)
for path in ('FROZEN_BASELINE.json', '05_KineticLoop_Protocol_v1.2_FROZEN.md',
             '04_KineticLoop_DB_Schema_Design_v0.2_FROZEN.md', 'CURRENT_REQUIREMENT_SET.json',
             'KineticLoop_Acceptance_Spec_v1.2.2.json', 'MILESTONE_CLOSURE.schema.json'):
    assert blob(path) == blob(path, BASE)

spec = importlib.util.spec_from_file_location('hg042_db_review_validator', ROOT / 'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
assert not v.governance_suffix_errors(ROOT, TESTED, REVIEWED, 'HG-042', 'tested')
old_src, new_src = blob('tools/harness/validate_harness.py', BASE).decode(), blob('tools/harness/validate_harness.py').decode()
functions = lambda source: {n.name: ast.get_source_segment(source, n) for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)}
old_functions, new_functions = functions(old_src), functions(new_src)
for name in ('integration_record_errors', 'review_evidence_exists', 'revision_regular_file', 'suffix_errors'):
    assert old_functions[name] == new_functions[name]
tasks = {t['id']: t for t in json.loads(blob(v.BACKLOG))['tasks']}
old_tasks = {t['id']: t for t in json.loads(blob(v.BACKLOG, BASE))['tasks']}
assert [name for name in tasks if tasks[name] != old_tasks[name]] == ['KL-028', 'KL-029']
namespace = {}
for task_id in ('KL-028', 'KL-029'):
    task = tasks[task_id]
    assert not v.m3_boundary_shadow_definition_errors(task)
    packet = blob(f'docs/exec-plans/active/{task_id}.md').decode()
    assert not v.packet_errors(task, packet)
    assert len(task['write_paths']) == 3 and task['shared_hotspot'] is False
    assert task['parallel_write_policy'] == 'PARALLEL_IF_DEPENDENCIES_MET'
    assert task['status'] == 'NOT_STARTED' and task['evidence_refs'] == []
    assert 'KL-027' in task['depends_on']
    namespace[task_id] = task['environment_requirements']
assert not set(tasks['KL-028']['write_paths']) & set(tasks['KL-029']['write_paths'])
assert not set(tasks['KL-028']['resource_keys']) & set(tasks['KL-029']['resource_keys'])
ledger = v.packet_json_section(blob('docs/exec-plans/active/KL-028.md').decode(), 'Boundary layer ledger')
requirements = json.loads(blob('KineticLoop_Acceptance_Spec_v1.2.2.json'))['supplemental_boundary_requirements']
assert not v.m3_boundary_layer_errors(ledger, requirements)
assert len(ledger) == 31 and all(row['status'] == 'NOT_RUN' for row in ledger)
assert sum(row['disposition'] == 'KL028_PLANNED_EXECUTABLE' for row in ledger) == 19
assert sum(row['disposition'] != 'KL028_PLANNED_EXECUTABLE' for row in ledger) == 12

checks = []
assert len(record['checks_run']) == 9
for command in record['checks_run']:
    ref = command['evidence_ref']
    evidence = json.loads(blob(ref))
    raw = evidence['raw_utf8'].encode()
    assert evidence['check_id'] == command['check_id']
    assert evidence['command'] == command['command']
    assert evidence['tested_commit'] == TESTED and evidence['base_commit'] == BASE
    assert evidence['result'] == command['result'] == 'PASS' and evidence['exit_code'] == 0
    assert evidence['evidence_ref'] == ref
    assert evidence['raw_byte_count'] == len(raw)
    assert evidence['raw_sha256'] == hashlib.sha256(raw).hexdigest()
    checks.append({'check_id': command['check_id'], 'evidence_ref': ref,
                   'raw_sha256': evidence['raw_sha256'], 'raw_byte_count': len(raw)})

schemas = [jsonschema.Draft202012Validator(json.loads(blob(p))) for p in
           ('INTEGRATION_RECORD.schema.json', 'THREAD_RESULT.schema.json', 'THREAD_REVIEW.schema.json')]
integrations = []
for task_id in ('KL-075', 'KL-076', 'KL-077', 'KL-079', 'KL-027'):
    ref = f'docs/exec-plans/integrations/{task_id}.json'
    item = json.loads(blob(ref))
    assert not v.integration_record_errors(ROOT, Path(ref), item, *schemas, tasks)
    merge = item['merge_commit']
    assert v.is_ancestor(ROOT, merge, BASE)
    parents = git('rev-list', '--parents', '-n', '1', merge).decode().split()[1:]
    assert len(parents) == 2 and parents[1] == item['review_record_commit']
    assert not v.suffix_errors(ROOT, item['reviewed_head_sha'], item['review_record_commit'], task_id, 'review')
    results = v.result_paths_at_revision(ROOT, task_id, item['result_commit'])
    assert len(results) == 1
    result_bytes = blob(results[0], item['result_commit'])
    assert result_bytes == blob(results[0], item['reviewed_head_sha']) == blob(results[0], merge) == blob(results[0], BASE)
    result = v.load_artifact_text(result_bytes.decode(), Path(results[0]).suffix)
    assert result['integration_status'] == 'UNMERGED' and result['task_status'] == 'PASS'
    sources = []
    for kind in tasks[task_id]['review_requirements']:
        review = json.loads(blob(f'docs/exec-plans/reviews/{task_id}/{kind}.json', item['review_record_commit']))
        assert review['status'] == 'PASS' and review['reviewed_head_sha'] == item['reviewed_head_sha']
        for source_ref in review['evidence_refs']:
            assert v.review_evidence_exists(ROOT, source_ref, item['reviewed_head_sha'], item['review_record_commit'], task_id, True)
            source = item['reviewed_head_sha'] if v.revision_regular_file(ROOT, source_ref, item['reviewed_head_sha']) else item['review_record_commit']
            raw = blob(source_ref, source)
            sources.append({'review_type': kind, 'path': source_ref, 'source_revision': source,
                            'sha256': hashlib.sha256(raw).hexdigest()})
    integrations.append({'task_id': task_id, 'record': item, 'result_sha256': hashlib.sha256(result_bytes).hexdigest(),
                         'historical_result_status': 'UNMERGED', 'review_sources': sources})

report = {'reviewed_head_sha': REVIEWED, 'protected_base': BASE, 'tested_commit': TESTED,
          'changed_paths': changed, 'no_production_migration_frozen_completed_edits': True,
          'tested_suffix_errors': [], 'hg043_provenance_functions_unchanged': True,
          'all_31_layers_not_run': True, 'planned_executable_layers': 19, 'deferred_layers': 12,
          'namespace_requirements': namespace, 'nine_final_raw_checks': checks,
          'integrations': integrations, 'db_or_lifecycle_invocations': 0}
(ROOT / HERE / 'audit.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'reviewed_head_sha': REVIEWED, 'final_check_count': len(checks),
                  'integration_count': len(integrations), 'layers': len(ledger),
                  'db_or_lifecycle_invocations': 0, 'result': 'PASS'}, indent=2))
