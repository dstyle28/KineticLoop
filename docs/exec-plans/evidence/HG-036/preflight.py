"""Read-only actual merged prerequisite and source boundary audit for HG036."""
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

import yaml

root = Path.cwd()
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
print('audited_commit=' + head)
spec = importlib.util.spec_from_file_location('validator', root / 'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
index = json.loads((root / 'CURRENT_DOCUMENT_INDEX.json').read_text())
for entry in index['documents'] + index['machine_readable']:
    assert hashlib.sha256((root / entry['path']).read_bytes()).hexdigest() == entry['sha256'], entry['path']
print('PASS indexed current source hashes')
for name, kinds in [('KL-005', ['GENERAL']), ('KL-018', ['GENERAL', 'PROTOCOL', 'DB_CONCURRENCY', 'SECURITY_DATA_BOUNDARY'])]:
    result_path = f'docs/exec-plans/completed/{name}_RESULT.yaml'
    result_bytes = (root / result_path).read_bytes()
    result = yaml.safe_load(result_bytes)
    integration = json.loads((root / f'docs/exec-plans/integrations/{name}.json').read_text())
    assert integration['task_identity'] == result['task_identity'] == 'harness-backlog-v0.2/' + name
    assert result['task_status'] == result['task_checks_status'] == 'PASS'
    assert integration['integration_status'] == 'MERGED'
    for left, right in [('result_commit', 'reviewed_head_sha'), ('reviewed_head_sha', 'review_record_commit')]:
        subprocess.run(['git', 'merge-base', '--is-ancestor', integration[left], integration[right]], check=True)
    subprocess.run(['git', 'merge-base', '--is-ancestor', integration['merge_commit'], head], check=True)
    edge = subprocess.run(['git', 'merge-base', '--is-ancestor', integration['review_record_commit'], integration['merge_commit']])
    if edge.returncode:
        assert subprocess.check_output(['git', 'rev-parse', integration['review_record_commit'] + '^{tree}']) == subprocess.check_output(['git', 'rev-parse', integration['merge_commit'] + '^{tree}'])
    for revision in ['result_commit', 'reviewed_head_sha']:
        assert subprocess.check_output(['git', 'show', integration[revision] + ':' + result_path]) == result_bytes
    assert v.suffix_errors(root, integration['reviewed_head_sha'], integration['review_record_commit'], name, 'review') == []
    for kind in kinds:
        review = json.loads((root / f'docs/exec-plans/reviews/{name}/{kind}.json').read_text())
        assert review['status'] == 'PASS' and review['reviewed_head_sha'] == integration['reviewed_head_sha']
        assert review['task_identity'] == result['task_identity']
    task = next(t for t in json.loads((root / v.BACKLOG).read_text())['tasks'] if t['id'] == name)
    assert {c['check_id'] for c in result['commands_run']} == set(task['checks_required_for_this_task'])
    assert len(result['commands_run']) == len(task['checks_required_for_this_task'])
    for command in result['commands_run']:
        assert command['result'] == 'PASS' and (root / command['evidence_ref']).is_file()
    assert all(r['status'] == 'NOT_RUN' for r in result['requirements_covered'])
    print('PASS actual result/checks/review/integration bindings ' + name + ' ' + json.dumps(integration, sort_keys=True))
for path, clauses in {
 '06_KineticLoop_Project_Plan_v0.6_HARNESS_HARDENED.md': ['### G-REMOTE-AI', 'fixed evaluation subset', 'refusal/bad-output/timeout', 'input/output evidence capture', 'predeclared scoring rules'],
 '05_KineticLoop_Protocol_v1.2_FROZEN.md': ['### 7.3', '### 7.5', '训练/调参/测试切分', '冻结时间', '泄漏检查'],
 '04_KineticLoop_DB_Schema_Design_v0.2_FROZEN.md': ['### S48', 'ReleaseEvaluationService.RecordRelease', '若无实测结果，不可声明 PASSED', '修改阈值或模型产生新 release'],
 '03_KineticLoop_Technical_Spec_v1.2.2_DEV_READY.md': ['## 11. Fitness proposal contract', 'Proposal content is immutable', 'does not issue approval/authorization'],
}.items():
    content = (root / path).read_text()
    for clause in clauses:
        assert clause in content, (path, clause)
    print('SOURCE ' + path + ' sha256=' + hashlib.sha256((root/path).read_bytes()).hexdigest())
assert not (root / 'src/kineticloop/evaluation').exists()
assert not (root / 'tests/evaluation').exists()
assert not list((root / 'docs/exec-plans/completed').glob('KL-047_RESULT.*'))
proposal = json.loads((root / 'docs/exec-plans/evidence/HG-036/KL047_definition_draft.json').read_text())
assert proposal['depends_on'] == ['KL-005', 'KL-018'] and proposal['conditional_depends_on'] == []
assert proposal['resource_keys'] == ['fitness_eval_contract'] and proposal['requirements_covered'] == []
kl019 = next(t for t in json.loads((root / v.BACKLOG).read_text())['tasks'] if t['id'] == 'KL-019')
assert not set(proposal['resource_keys']) & set(kl019['resource_keys'])
for left in proposal['write_paths']:
    for right in kl019['write_paths']:
        assert left != right and not v.matches(left, [right]) and not v.matches(right, [left])
print('PASS prospective KL047 exact write/resource scope independent of current KL019; recheck after HG035 merge')
print('LIMITATION no typed FitnessProposal/expert labels/rubric/sample-size/weights/quality thresholds provided by cited sources')
print('NOT_RUN all prospective KL047 task checks; product/gate/release/quality/model obligations remain NOT_RUN')
