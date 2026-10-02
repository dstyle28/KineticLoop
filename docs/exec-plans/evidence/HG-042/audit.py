"""Audit bounded governance scope, immutable completed tasks and HG043 preservation."""
import ast
import json
import subprocess
from pathlib import Path

ROOT = Path.cwd()
BASE = '93b38f20a3f3d71206515fb0f4d852f5b0b6d344'
git = lambda *args: subprocess.check_output(['git', *args], cwd=ROOT)
old = json.loads(git('show', BASE + ':KineticLoop_Harness_Backlog_v0.2.json'))
new = json.loads((ROOT / 'KineticLoop_Harness_Backlog_v0.2.json').read_text())
before = {t['id']: t for t in old['tasks']}
after = {t['id']: t for t in new['tasks']}
assert list(before) == list(after)
changed_tasks = [n for n in before if before[n] != after[n]]
assert changed_tasks == ['KL-028', 'KL-029']
assert {k: v for k, v in old.items() if k != 'tasks'} == {k: v for k, v in new.items() if k != 'tasks'}
for name in changed_tasks:
    assert after[name]['status'] == 'NOT_STARTED' and after[name]['evidence_refs'] == []
    assert before[name]['requirements_covered'] == after[name]['requirements_covered']
    assert set(before[name]['review_requirements']) <= set(after[name]['review_requirements'])
files = git('diff', '--name-only', BASE, 'HEAD').decode().splitlines()
exact = {
    '06_KineticLoop_Project_Plan_v0.6_HARNESS_HARDENED.md', 'CURRENT_DOCUMENT_INDEX.json',
    'HARNESS_DOCUMENT_MANIFEST.json', 'KineticLoop_Harness_Backlog_v0.2.json',
    'KineticLoop_Harness_Traceability_v0.3.json', 'docs/exec-plans/active/KL-028.md',
    'docs/exec-plans/active/KL-029.md', 'docs/harness/RESOURCE_LOCKS.md',
    'tools/harness/validate_harness.py', 'tests/harness/test_m3_boundary_shadow_scope.py',
    'docs/exec-plans/governance/HG-042.yaml',
} | {f'docs/exec-plans/integrations/KL-{n:03}.json' for n in (75, 76, 77, 79, 27)}
assert all(p in exact or p.startswith(('docs/exec-plans/evidence/HG-042/',
                                      'docs/exec-plans/reviews/HG-042/')) for p in files), files
assert not any(p.startswith(('docs/exec-plans/completed/', 'src/', 'migrations/', '.github/')) for p in files)
for path in ('05_KineticLoop_Protocol_v1.2_FROZEN.md', '04_KineticLoop_DB_Schema_Design_v0.2_FROZEN.md',
             'FROZEN_BASELINE.json', 'MILESTONE_CLOSURE.schema.json', 'CURRENT_REQUIREMENT_SET.json',
             'KineticLoop_Acceptance_Spec_v1.2.2.json', 'docs/harness/THREAD_REVIEW_CONTRACT.md',
             'docs/harness/HARNESS_GOVERNANCE_CONTRACT.md'):
    assert git('show', BASE + ':' + path) == (ROOT / path).read_bytes(), path
path = 'tools/harness/validate_harness.py'
old_source = git('show', BASE + ':' + path).decode()
new_source = (ROOT / path).read_text()
old_functions = {n.name: ast.get_source_segment(old_source, n) for n in ast.parse(old_source).body if isinstance(n, ast.FunctionDef)}
new_functions = {n.name: ast.get_source_segment(new_source, n) for n in ast.parse(new_source).body if isinstance(n, ast.FunctionDef)}
for name in ('integration_record_errors', 'review_evidence_exists', 'revision_regular_file', 'suffix_errors'):
    assert old_functions[name] == new_functions[name], name
records = [f'docs/exec-plans/integrations/KL-{n:03}.json' for n in (75, 76, 77, 79, 27)]
assert all((ROOT / p).is_file() for p in records)
assert all(after[n]['shared_hotspot'] is False for n in changed_tasks)
assert not set(after['KL-028']['write_paths']) & set(after['KL-029']['write_paths'])
assert not set(after['KL-028']['resource_keys']) & set(after['KL-029']['resource_keys'])
print(json.dumps({'protected_base': BASE, 'head': git('rev-parse', 'HEAD').decode().strip(),
                  'changed_task_definitions': changed_tasks, 'changed_files': files,
                  'hg043_provenance_functions_byte_identical': True,
                  'completed_task_artifacts_unchanged': True, 'all_prospective_checks': 'NOT_RUN',
                  'product_m3_release_pass_claims': []}, indent=2))
