"""Independent Git-blob and raw-witness security review audit; no DB lifecycle."""
import collections
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[5]
REVIEWED = 'eed165afbd56d3ae551c46166aaec776cf79e625'
TESTED = 'b9fbf9b475e07765db62e67f0104a800036dda4d'
BASE = '9268fc8dd8c071c02dc5c698274dbf6fcd112776'
OWN = 'docs/exec-plans/reviews/KL-029/security-raw/'

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)

def blob(path, rev=REVIEWED):
    entry = git('ls-tree', rev, '--', path).decode().split()
    assert entry[0] in ('100644', '100755') and entry[1] == 'blob'
    return git('show', rev + ':' + path)

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

for older, newer in ((BASE, TESTED), (TESTED, REVIEWED)):
    subprocess.run(['git', 'merge-base', '--is-ancestor', older, newer], cwd=ROOT, check=True)
suffix = git('rev-list', '--reverse', TESTED + '..' + REVIEWED).decode().splitlines()
suffix_paths = {}
for commit in suffix:
    assert len(git('rev-list', '--parents', '-n', '1', commit).split()) == 2
    changed = git('diff-tree', '--no-commit-id', '--name-status', '-r', commit).decode().splitlines()
    for line in changed:
        status, path = line.split('\t')
        assert path == 'docs/exec-plans/completed/KL-029_RESULT.yaml' or (status == 'A' and path.startswith('docs/exec-plans/evidence/KL-029/'))
    suffix_paths[commit] = changed
implementation = ['tests/db/test_shadow_isolation.py', 'tests/unit/protocol/test_shadow_isolation.py', 'docs/contracts/shadow_isolation.md']
assert not git('diff', '--name-only', TESTED, REVIEWED, '--', *implementation)
changed = git('diff', '--name-only', BASE, REVIEWED).decode().splitlines()
assert all(p in implementation or p == 'docs/exec-plans/completed/KL-029_RESULT.yaml' or p.startswith('docs/exec-plans/evidence/KL-029/') for p in changed)
index = json.loads(blob('CURRENT_DOCUMENT_INDEX.json'))
for entry in index['documents'] + index['machine_readable']:
    assert hashlib.sha256(blob(entry['path'])).hexdigest() == entry['sha256'], entry['path']
result = yaml.safe_load(blob('docs/exec-plans/completed/KL-029_RESULT.yaml'))
jsonschema.validate(result, json.loads(blob('THREAD_RESULT.schema.json')))
assert result['task_identity'] == 'harness-backlog-v0.2/KL-029'
assert result['base_commit'] == BASE and result['tested_commit'] == TESTED
assert result['task_status'] == result['task_checks_status'] == 'PASS'
assert result['requirements_covered'] == []
packet = blob('docs/exec-plans/active/KL-029.md').decode()
checks = json.loads(re.search(r'```json\n(.*?)\n```', packet, re.S).group(1))['check_contracts']
records = json.loads(blob('docs/exec-plans/evidence/KL-029/checks-b9fbf9b/checks.json'))
assert records['tested_commit'] == TESTED
assert {c['check_id']:c['command'] for c in checks} == {c['check_id']:c['command'] for c in result['commands_run']} == {c['check_id']:c['command'] for c in records['checks']}
log_summary = []
all_witnesses = []
for check in records['checks']:
    raw = blob(check['evidence_ref'])
    assert hashlib.sha256(raw).hexdigest() == check['log_sha256']
    assert check['result'] == 'PASS' and check['exit_code'] == 0
    lines = raw.decode().splitlines()
    header = json.loads(lines[0])
    assert header['tested_commit'] == TESTED and header['command'] == check['command']
    if check['junit_ref']:
        suites = list(ET.fromstring(blob(check['junit_ref'])).iter('testsuite'))
        counts = {k:sum(int(s.get(k, '0')) for s in suites) for k in ('tests','failures','errors','skipped')}
        assert counts == check['counts'] and counts['tests'] > 0
        assert counts['failures'] == counts['errors'] == counts['skipped'] == 0
        assert not any(t.find('skipped') is not None for s in suites for t in s.findall('testcase'))
    witnesses = [json.loads(l[len('SHADOW_EVIDENCE '):]) for l in lines if l.startswith('SHADOW_EVIDENCE ')]
    all_witnesses.extend(witnesses)
    log_summary.append({'check_id':check['check_id'], 'sha256':check['log_sha256'], 'counts':check['counts'], 'witness_counts':dict(collections.Counter(w['kind'] for w in witnesses))})
suite = [json.loads(l[len('SHADOW_EVIDENCE '):]) for l in blob('docs/exec-plans/evidence/KL-029/checks-b9fbf9b/shadow_suite_dc.log').decode().splitlines() if l.startswith('SHADOW_EVIDENCE ')]
counts = collections.Counter(w['kind'] for w in suite)
assert counts['zero_effect'] == 26 and counts['live_privilege_denial'] == 15 and counts['scope_denial'] == 27
assert counts['full_TEST_owner_trajectory'] == counts['cleanup'] == 4 and counts['actual_T7_positive_guard'] == 12
for w in all_witnesses:
    assert w['tested_commit'] == TESTED
    kind = w['kind']
    if kind == 'zero_effect':
        assert w['before'] == w['after'] and w['zero_new_receipt_event_outbox']
    elif kind == 'scope_denial':
        assert w['code'] == 'SUBJECT_SCOPE_DENIED' and w['response'] == {'error':'subject_scope_denied'}
        assert w['timing_class'] == 'BOUNDED_SCOPE_LOOKUP' and not w['measured_constant_time']
    elif kind == 'live_privilege_denial':
        assert w['sqlstate'] == '42501' and w['guard_reached'] == 'DB_table_privilege'
        assert w['table'] in ('daily_plan_heads','authorization_issuances','execution_bindings')
    elif kind == 'cleanup':
        assert not any(w['remaining'].values())
    elif kind == 'actual_T7_positive_guard':
        assert w['decision']['is_executable'] and w['decision']['non_bearer']
    elif kind == 'declared_external_evaluation_inputs':
        assert w['source']['classification'] == 'EXTERNAL_HISTORICAL_INPUT_ONLY'
        assert w['source']['mode'] == 'RECORDED_OUTPUT' and w['source']['execution_disposition'] == 'NOT_EXECUTABLE'
        assert w['source']['knowledge_cutoff'] and w['source']['source_ref']
        assert w['no_live_pointer_or_shadow_owner_output'] and all(t[2] in ('O','A') for t in w['triggers'])
        for table, record in w['persisted'].items():
            assert digest(record['row']) == record['row_hash']
            if table != 'safety_artifacts':
                assert record['row']['subject_id'] == w['subject']
        p = {t:v['row'] for t,v in w['persisted'].items()}
        assert p['replay_artifacts']['ref_s46_id'] == p['replay_runs']['id']
        assert p['replay_runs']['ref_s24_id'] == p['decision_manifests']['id']
        assert p['replay_runs']['ref_s48_id'] == p['evaluation_releases']['id']
    elif kind == 'full_TEST_owner_trajectory':
        h = w['immutable_history']
        rows = {t:[r[0] for r in v] for t,v in h.items() if isinstance(v,list)}
        assert len(rows['authorization_issuances']) == 2 and len(rows['execution_bindings']) == 2
        assert [m['action_type'] for m in w['T6']['members']] == ['TRAINING','NUTRITION']
        assert rows['planning_intents'][0]['status'] == 'FOUND_VALID_PLAN'
        reg = rows['scope_registrations'][0]
        assert reg['namespace'] == 'TEST'
        assert rows['principal_bindings'][0]['principal_name'] == 'kl_test_subject_1_login'
        for a in rows['authorization_issuances']:
            assert a['scope'] == 'TEST_ONLY' and a['ref_s05_id'] == reg['policy_id']
            assert digest(a['validity_certificate']['dependencies']) == w['T6']['artifact_dependency_closure_hash']
        receipts = rows['command_receipts']; events = rows['domain_events']; outbox = rows['outbox_deliveries']
        assert len(receipts) == len(events) == len(outbox)
        for receipt in receipts:
            linked = [e for e in events if e['ref_s02_id'] == receipt['id']]
            assert len(linked) == 1 and len([o for o in outbox if o['ref_s03_id'] == linked[0]['id']]) == 1
        for command in ('T6','START','CONTINUE','PAUSE','RESUME'):
            assert w[command]['receipt_id'] in {r['id'] for r in receipts}
            assert w[command]['event_id'] in {e['id'] for e in events}
        for name, table in (('fitness','proposal_revisions'),('nutrition','proposal_revisions'),('demand','prescription_demand_features'),('snapshot','decision_snapshots'),('resolution','evidence_resolutions'),('nutrition_resolution','evidence_resolutions'),('validation','validation_results')):
            assert w['sources'][name]['id'] in {r['id'] for r in rows[table]}
pure = list(ET.parse(ROOT / OWN / 'pu.xml').getroot().iter('testsuite'))
assert sum(int(s.get('tests','0')) for s in pure) == 2 and all(int(s.get(k,'0')) == 0 for s in pure for k in ('failures','errors','skipped'))
report = {'reviewed_head_sha':REVIEWED,'tested_commit':TESTED,'protected_base':BASE,'implementation_equal_at_tested_and_reviewed':True,'linear_result_evidence_suffix':suffix_paths,'changed_paths':changed,'authority_hashes_verified':True,'schema_valid_result':True,'product_pass_claims':[],'committed_checks':log_summary,'suite_witness_counts':dict(counts),'suite_guard_counts':dict(collections.Counter(w['guard_reached'] for w in suite if 'guard_reached' in w)),'fresh_pure_checks':{'tests':2,'failures':0,'errors':0,'skipped':0},'fresh_DB_rerun':False,'DB_rerun_reason':'exclusive resource owned by DB reviewer; source and committed raw evidence audited independently'}
(ROOT / OWN / 'audit.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
