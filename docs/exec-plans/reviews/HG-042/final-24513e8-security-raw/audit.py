"""Independent HG042 security review checks; reads Git blobs, no DB lifecycle."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[5]
BASE = '93b38f20a3f3d71206515fb0f4d852f5b0b6d344'
TESTED = 'e4134f963450db1522fd6c3339e4cb036fcf5ffe'
REVIEWED = '24513e86d90799edb951fa2bdf52ba433c59318a'
def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)
def blob(path, revision=REVIEWED):
    entry = git('ls-tree', revision, '--', path).decode().strip().split()
    assert entry and entry[0] in ('100644', '100755') and entry[1] == 'blob', path
    return git('show', revision + ':' + path)

assert git('rev-parse', 'HEAD').decode().strip() == REVIEWED
for a, b in ((BASE, TESTED), (TESTED, REVIEWED)):
    git('merge-base', '--is-ancestor', a, b)
spec = importlib.util.spec_from_file_location('security_review_validator', ROOT / 'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
assert not v.governance_suffix_errors(ROOT, TESTED, REVIEWED, 'HG-042', 'tested')
record = yaml.safe_load(blob('docs/exec-plans/governance/HG-042.yaml'))
assert record['base_commit'] == BASE and record['tested_commit'] == TESTED
changed = git('diff', '--name-only', BASE, REVIEWED).decode().splitlines()
assert sorted(changed) == sorted(record['files_changed'])
assert not any(p.startswith(('src/', 'migrations/', '.github/', 'docs/exec-plans/completed/')) for p in changed)
protected = ['05_KineticLoop_Protocol_v1.2_FROZEN.md', '04_KineticLoop_DB_Schema_Design_v0.2_FROZEN.md', 'FROZEN_BASELINE.json', 'CURRENT_REQUIREMENT_SET.json', 'KineticLoop_Acceptance_Spec_v1.2.2.json', 'THREAD_REVIEW.schema.json', 'docs/harness/THREAD_REVIEW_CONTRACT.md', 'docs/harness/HARNESS_GOVERNANCE_CONTRACT.md']
for p in protected:
    assert blob(p, BASE) == blob(p)
before = {t['id']: t for t in json.loads(blob(v.BACKLOG, BASE))['tasks']}
tasks = {t['id']: t for t in json.loads(blob(v.BACKLOG))['tasks']}
assert [n for n in tasks if tasks[n] != before[n]] == ['KL-028', 'KL-029']
for n in ('KL-028', 'KL-029'):
    task = tasks[n]
    packet = blob(f'docs/exec-plans/active/{n}.md').decode()
    assert task['status'] == 'NOT_STARTED' and task['evidence_refs'] == []
    assert before[n]['requirements_covered'] == task['requirements_covered']
    assert set(before[n]['review_requirements']) <= set(task['review_requirements'])
    assert not v.m3_boundary_shadow_definition_errors(task)
    assert not v.packet_errors(task, packet)
    assert set(v.packet_json_section(packet, 'Prospective check status').values()) == {'NOT_RUN'}
assert not set(tasks['KL-028']['write_paths']) & set(tasks['KL-029']['write_paths'])
assert not set(tasks['KL-028']['resource_keys']) & set(tasks['KL-029']['resource_keys'])
ledger = v.packet_json_section(blob('docs/exec-plans/active/KL-028.md').decode(), 'Boundary layer ledger')
reqs = json.loads(blob('KineticLoop_Acceptance_Spec_v1.2.2.json'))['supplemental_boundary_requirements']
assert not v.m3_boundary_layer_errors(ledger, reqs)
assert len(ledger) == 31 and sum(r['disposition'] == 'KL028_PLANNED_EXECUTABLE' for r in ledger) == 19
assert all(r['status'] == 'NOT_RUN' for r in ledger)
shadow = blob('docs/exec-plans/active/KL-029.md').decode()
for phrase in ('no measured constant-time claim', 'genuine valid ProductionScope command', 'strict public command parser rejects shadow scope', 'archived S24/S48/FK backing closure', 'FK checks and triggers enabled', 'no session_replication_role bypass or global revision reset', 'distinct reach labels', 'KL045', 'full before/after history snapshots', 'Fresh command keys'):
    assert phrase in shadow, phrase
evidence = []
for check in record['checks_run']:
    raw = json.loads(blob(check['evidence_ref']))
    encoded = raw['raw_utf8'].encode()
    assert raw['tested_commit'] == TESTED and raw['base_commit'] == BASE
    assert check['result'] == raw['result'] == 'PASS' and raw['exit_code'] == 0
    assert hashlib.sha256(encoded).hexdigest() == raw['raw_sha256']
    assert len(encoded) == raw['raw_byte_count']
    assert raw['command'] == check['command']
    evidence.append({'check_id': check['check_id'], 'raw_sha256': raw['raw_sha256'], 'raw_byte_count': len(encoded)})
schemas = [jsonschema.Draft202012Validator(json.loads(blob(p))) for p in ('INTEGRATION_RECORD.schema.json', 'THREAD_RESULT.schema.json', 'THREAD_REVIEW.schema.json')]
integrations = []
for n in ('KL-027', 'KL-075', 'KL-076', 'KL-077', 'KL-079'):
    path = f'docs/exec-plans/integrations/{n}.json'
    r = json.loads(blob(path))
    assert not v.integration_record_errors(ROOT, Path(path), r, *schemas, tasks)
    parents = git('rev-list', '--parents', '-n', '1', r['merge_commit']).decode().split()[1:]
    assert len(parents) == 2 and r['review_record_commit'] == parents[1]
    git('merge-base', '--is-ancestor', r['merge_commit'], BASE)
    assert not v.suffix_errors(ROOT, r['reviewed_head_sha'], r['review_record_commit'], n, 'review')
    result_paths = v.result_paths_at_revision(ROOT, n, r['result_commit'])
    assert len(result_paths) == 1
    result = yaml.safe_load(blob(result_paths[0], r['result_commit']))
    assert result['integration_status'] == 'UNMERGED' and result['task_status'] == 'PASS'
    assert blob(result_paths[0], r['result_commit']) == blob(result_paths[0], BASE) == blob(result_paths[0])
    counts = {'REVIEWED': 0, 'REVIEW_RECORD_ONLY': 0}
    for kind in tasks[n]['review_requirements']:
        review = json.loads(blob(f'docs/exec-plans/reviews/{n}/{kind}.json', r['review_record_commit']))
        assert review['status'] == 'PASS' and review['reviewed_head_sha'] == r['reviewed_head_sha']
        for ref in review['evidence_refs']:
            assert v.review_evidence_exists(ROOT, ref, r['reviewed_head_sha'], r['review_record_commit'], n, True)
            source = r['reviewed_head_sha'] if v.revision_regular_file(ROOT, ref, r['reviewed_head_sha']) else r['review_record_commit']
            blob(ref, source)
            counts['REVIEWED' if source == r['reviewed_head_sha'] else 'REVIEW_RECORD_ONLY'] += 1
    integrations.append({'task_id': n, 'merge_commit': r['merge_commit'], 'normal_merge': True, 'reference_counts': counts, 'historical_result_unchanged': True})
source_paths = ['src/kineticloop/contracts/shadow.py', 'src/kineticloop/contracts/commands.py', 'src/kineticloop/protocol/execution.py', 'src/kineticloop/persistence/protocol_execution.py', 'src/kineticloop/persistence/subject_scope.py', 'src/kineticloop/persistence/transactions.py', 'migrations/versions/d4c1a9e7b203_subject_scope.py', 'migrations/versions/76fd67f76bd4_frozen_s01_s51_baseline.py']
sources = {}
for p in source_paths:
    raw = blob(p)
    assert raw == blob(p, BASE) == blob(p, TESTED) == (ROOT / p).read_bytes()
    sources[p] = hashlib.sha256(raw).hexdigest()
print(json.dumps({'reviewed_head_sha': REVIEWED, 'tested_commit': TESTED, 'protected_base': BASE, 'checks': 'PASS', 'declared_changed_files': len(changed), 'changed_tasks': ['KL-028', 'KL-029'], 'boundary_layers': {'total': 31, 'prospective_executable': 19, 'deferred': 12, 'all_statuses': 'NOT_RUN'}, 'evidence': evidence, 'integrations': integrations, 'source_sha256': sources, 'db_runtime_executed': False}, indent=2))
