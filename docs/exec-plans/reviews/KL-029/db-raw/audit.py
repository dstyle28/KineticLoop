"""Independent read-only KL029 DB review evidence audit."""
import collections
import hashlib
import json
import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[5]
BASE = '9268fc8dd8c071c02dc5c698274dbf6fcd112776'
REVIEW = 'eed165afbd56d3ae551c46166aaec776cf79e625'
TESTED = 'b9fbf9b475e07765db62e67f0104a800036dda4d'
OUT = Path(__file__).parent

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()

def stats(path):
    suites = list(ET.parse(path).getroot().iter('testsuite'))
    return {k: sum(int(s.get(k, '0')) for s in suites) for k in ('tests', 'errors', 'failures', 'skipped')}

def events(path):
    result = []
    for line in path.read_text().splitlines():
        prefix = 'SHADOW_EVIDENCE '
        if prefix in line:
            result.append(json.loads(line.split(prefix, 1)[1]))
    return result

assert git('rev-parse', 'HEAD') == REVIEW
for a,b in ((BASE,TESTED),(TESTED,REVIEW)):
    subprocess.run(['git','merge-base','--is-ancestor',a,b],cwd=ROOT,check=True)
suffix = git('rev-list','--reverse',TESTED+'..'+REVIEW).splitlines()
for sha in suffix:
    assert len(git('show','-s','--format=%P',sha).split()) == 1
    for row in git('diff-tree','--no-commit-id','--name-status','-r',sha).splitlines():
        mode,path = row.split('\t')
        assert mode == 'A' and (path == 'docs/exec-plans/completed/KL-029_RESULT.yaml' or path.startswith('docs/exec-plans/evidence/KL-029/'))
prerequisites = {}
for task in ('KL-008','KL-017','KL-027'):
    data = json.loads(git('show',BASE+':docs/exec-plans/integrations/'+task+'.json'))
    assert data['integration_status'] == 'MERGED'
    merge = data['merge_commit']
    assert len(git('show','-s','--format=%P',merge).split()) == 2
    subprocess.run(['git','merge-base','--is-ancestor',merge,BASE],cwd=ROOT,check=True)
    reviews = {}
    for path in git('ls-tree','-r','--name-only',data['review_record_commit'],'docs/exec-plans/reviews/'+task).splitlines():
        if path.endswith('.json') and '/history/' not in path:
            obj = json.loads(git('show',data['review_record_commit']+':'+path))
            if isinstance(obj, dict) and obj.get('review_type'):
                assert obj['reviewed_head_sha'] == data['reviewed_head_sha'] and obj['status'] == 'PASS'
                reviews[obj['review_type']] = obj['status']
    prerequisites[task] = {'merge_commit':merge,'reviews':reviews}
assert json.loads(git('show',BASE+':docs/exec-plans/milestones/M2.json'))['closure_status'] == 'PASS'
author = json.loads((ROOT/'docs/exec-plans/evidence/KL-029/checks-b9fbf9b/checks.json').read_text())
assert author['tested_commit'] == TESTED and len(author['checks']) == 12
for check in author['checks']:
    assert check['result'] == 'PASS' and check['exit_code'] == 0
    path = ROOT/check['evidence_ref']
    assert hashlib.sha256(path.read_bytes()).hexdigest() == check['log_sha256']
    if check['junit_ref']:
        counts = stats(ROOT/check['junit_ref'])
        assert counts == check['counts'] and counts['tests'] > 0
        assert counts['errors'] == counts['failures'] == counts['skipped'] == 0

raw = OUT/'suite-escalated.log'
items = events(raw)
count = collections.Counter(x['kind'] for x in items)
assert all(x['tested_commit'] == REVIEW for x in items)
assert stats(OUT/'suite-escalated.xml') == {'tests':6,'errors':0,'failures':0,'skipped':0}
token = hashlib.sha256(os.fsencode(ROOT.resolve())).hexdigest()[:12]
expected_compose = 'kineticloop-kl029-shadow-'+REVIEW[:7]+'-'+token
expected_database = expected_compose.replace('-','_')
assert count['namespace'] == count['cleanup'] == count['full_TEST_owner_trajectory'] == 4
guards = collections.Counter()
trajectories = []
for item in items:
    if item['kind'] == 'namespace':
        assert item['compose'] == expected_compose and item['database'] == expected_database
        assert item['root'] == str(ROOT.resolve()) and item['migration'] == 'e8c2f1a6b904'
        assert item['lifecycle'] == ['bootstrap_two_phase(selected_lifecycle)','reset','start']
    if item['kind'] == 'cleanup':
        assert item['remaining'] == {'container':'','volume':'','network':''}
        assert item['inventory'][-1] == 'destroy'
    if item['kind'] == 'zero_effect':
        assert item['before'] == item['after'] and item['zero_new_receipt_event_outbox']
        guards[item['guard_reached']] += 1
    if item['kind'] == 'live_privilege_denial':
        assert item['sqlstate'] == '42501' and item['guard_reached'] == 'DB_table_privilege'
    if item['kind'] == 'scope_denial':
        assert item['code'] == 'SUBJECT_SCOPE_DENIED' and item['response'] == {'error':'subject_scope_denied'}
        assert item['timing_class'] == 'BOUNDED_SCOPE_LOOKUP' and item['measured_constant_time'] is False
    if item['kind'] == 'actual_T7_positive_guard':
        assert item['decision']['is_executable']
    if item['kind'] == 'full_TEST_owner_trajectory':
        history = item['immutable_history']
        assert len(history['authorization_issuances']) == 2 and len(history['execution_bindings']) == 2
        assert {r[0]['binding_kind'] for r in history['execution_bindings']} == {'START','RESUME'}
        assert len(item['T6']['members']) == 2
        assert all(item[k]['executable'] for k in ('START','CONTINUE','RESUME'))
        trajectories.append({'sources':item['sources'],'members':item['T6']['members'], 'session_id':item['START']['session_id'], 'bindings':[r[0]['id'] for r in history['execution_bindings']], 'receipt_event_outbox_count':len(history['command_receipts'])})
assert count['actual_T7_positive_guard'] == 12
assert count['zero_effect'] == 26 and count['live_privilege_denial'] == 15 and count['scope_denial'] == 27
assert guards == {'registration_guard':3,'require_wire':5,'owner_current_bundle_pre_T7':1,'strict_owner_ingress':10,'DB_storage_namespace':7}
report = {'reviewed_head_sha':REVIEW,'tested_commit':TESTED,'protected_base':BASE,'prerequisites':prerequisites,'tested_to_reviewed_suffix':suffix,'author_checks_verified':12,'independent_suite_counts':stats(OUT/'suite-escalated.xml'),'compose':expected_compose,'database':expected_database,'raw_counts':dict(count),'zero_effect_guard_counts':dict(guards),'trajectories':trajectories,'raw_sha256':hashlib.sha256(raw.read_bytes()).hexdigest(),'initial_sandbox_attempt':'2 PU passed, 4 DB setup errors due Docker API permission; no DB case reached; approved ordinary escalation rerun passed','frozen_source_migration_grant_lifecycle_CI_changes':False,'product_layer_pass_claims':[]}
(OUT/'audit.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ('independent_suite_counts','raw_counts','zero_effect_guard_counts','author_checks_verified')}))
