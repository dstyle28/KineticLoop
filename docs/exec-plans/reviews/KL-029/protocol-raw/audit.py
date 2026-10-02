"""Independent PROTOCOL evidence audit; no DB/lifecycle operations."""
import collections
import hashlib
import json
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
REVIEWED = 'eed165afbd56d3ae551c46166aaec776cf79e625'
BASE = '9268fc8dd8c071c02dc5c698274dbf6fcd112776'
TESTED = 'b9fbf9b475e07765db62e67f0104a800036dda4d'

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)

def blob(path, sha=REVIEWED):
    return git('show', sha + ':' + path)

def witness(log, prefix):
    return [json.loads(line[len(prefix):]) for line in log.splitlines() if line.startswith(prefix)]

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

assert git('rev-parse', 'HEAD').decode().strip() == REVIEWED
assert subprocess.run(['git', 'merge-base', '--is-ancestor', TESTED, REVIEWED], cwd=ROOT).returncode == 0
implementation = ['tests/db/test_shadow_isolation.py', 'tests/unit/protocol/test_shadow_isolation.py', 'docs/contracts/shadow_isolation.md']
for path in implementation:
    assert blob(path) == blob(path, TESTED)
changed = git('diff', '--name-only', BASE, REVIEWED).decode().splitlines()
assert all(p in implementation or p == 'docs/exec-plans/completed/KL-029_RESULT.yaml' or p.startswith('docs/exec-plans/evidence/KL-029/') for p in changed)
assert not git('diff', BASE, REVIEWED, '--', 'src', 'migrations', 'FROZEN_BASELINE.json', 'CURRENT_REQUIREMENT_SET.json', '.github', 'tools', 'CURRENT_DOCUMENT_INDEX.json')

entry = json.loads(blob('docs/exec-plans/evidence/KL-029/entry-audit.json'))
prerequisites = []
for item in entry['prerequisites']:
    assert item['task_identity'].startswith('harness-backlog-v0.2/')
    assert subprocess.run(['git', 'merge-base', '--is-ancestor', item['merge_commit'], BASE], cwd=ROOT).returncode == 0
    parents = git('show', '-s', '--format=%P', item['merge_commit']).decode().split()
    assert len(parents) == 2 and parents[1] == item['review_record_commit']
    task = item['display_task_id']
    for review in ('GENERAL', 'PROTOCOL', 'DB_CONCURRENCY'):
        record = json.loads(blob(f'docs/exec-plans/reviews/{task}/{review}.json', BASE))
        assert record['status'] == 'PASS' and record['reviewed_head_sha'] == item['reviewed_head_sha']
    suffix = git('diff', '--name-only', item['reviewed_head_sha'], item['review_record_commit']).decode().splitlines()
    assert all(p.startswith(f'docs/exec-plans/reviews/{task}/') for p in suffix)
    prerequisites.append({'task': task, 'normal_merge': item['merge_commit'], 'sha_bound_reviews': True})

packet = blob('docs/exec-plans/active/KL-029.md').decode()
contracts = json.loads(re.search(r'```json\n(.*?)\n```', packet, re.S).group(1))['check_contracts']
manifest = json.loads(blob('docs/exec-plans/evidence/KL-029/checks-b9fbf9b/checks.json'))
assert manifest['tested_commit'] == TESTED
assert len(manifest['checks']) == len(contracts) == 12
checks = []
for expected, record in zip(contracts, manifest['checks'], strict=True):
    assert record['check_id'] == expected['check_id'] and record['command'] == expected['command']
    assert record['result'] == 'PASS' and record['exit_code'] == 0
    raw = blob(record['evidence_ref'])
    assert hashlib.sha256(raw).hexdigest() == record['log_sha256']
    metadata = json.loads(raw.splitlines()[0])
    assert metadata['tested_commit'] == TESTED and metadata['command'] == expected['command']
    counts = None
    if record['junit_ref']:
        suites = list(ET.fromstring(blob(record['junit_ref'])).iter('testsuite'))
        counts = {k: sum(int(s.get(k, '0')) for s in suites) for k in ('tests', 'failures', 'errors', 'skipped')}
        assert counts == record['counts'] and counts['tests'] > 0
        assert counts['failures'] == counts['errors'] == counts['skipped'] == 0
        assert all(not c.findall('skipped') for s in suites for c in s.findall('testcase'))
    checks.append({'check': record['check_id'], 'hash_valid': True, 'counts': counts})

log = blob('docs/exec-plans/evidence/KL-029/checks-b9fbf9b/shadow_suite_dc.log').decode()
rows = witness(log, 'SHADOW_EVIDENCE ')
fixtures = witness(log, 'FIXTURE_EVIDENCE ')
counts = collections.Counter(r['kind'] for r in rows)
assert counts['full_TEST_owner_trajectory'] == 4 and counts['actual_T7_positive_guard'] == 12
assert counts['live_privilege_denial'] == 15 and counts['zero_effect'] == 26
assert counts['scope_denial'] == 27 and counts['cleanup'] == 4
for r in rows:
    assert r['tested_commit'] == TESTED
    if r['kind'] == 'zero_effect':
        assert r['before'] == r['after'] and r['zero_new_receipt_event_outbox'] is True
    elif r['kind'] == 'cleanup':
        assert not any(r['remaining'].values())
    elif r['kind'] == 'actual_T7_positive_guard':
        assert r['decision']['is_executable'] is True
    elif r['kind'] == 'scope_denial':
        assert r['response'] == {'error': 'subject_scope_denied'}
        assert r['timing_class'] == 'BOUNDED_SCOPE_LOOKUP' and not r['measured_constant_time']
    elif r['kind'] == 'declared_external_evaluation_inputs':
        assert r['source']['classification'] == 'EXTERNAL_HISTORICAL_INPUT_ONLY'
        assert r['source']['mode'] == 'RECORDED_OUTPUT'
        assert r['source']['execution_disposition'] == 'NOT_EXECUTABLE'
        assert r['source']['knowledge_cutoff'] and r['no_live_pointer_or_shadow_owner_output']
        assert all(t[2] in ('O', 'A') for t in r['triggers'])
        persisted = r['persisted']
        assert set(persisted) == {'policy_bundles', 'program_versions', 'factset_revisions', 'projection_versions', 'manifest_builds', 'evaluation_releases', 'safety_artifacts', 'decision_manifests', 'replay_runs', 'replay_artifacts'}
        for table, item in persisted.items():
            assert digest(item['row']) == item['row_hash']
            assert item['row']['typed_payload'] == r['source']
            if table != 'safety_artifacts':
                assert item['row']['subject_id'] == r['subject']
        assert persisted['replay_runs']['row']['ref_s24_id'] == persisted['decision_manifests']['row']['id']
        assert persisted['replay_runs']['row']['ref_s48_id'] == persisted['evaluation_releases']['row']['id']
        assert persisted['replay_artifacts']['row']['ref_s46_id'] == persisted['replay_runs']['row']['id']
    elif r['kind'] == 'namespace':
        token = hashlib.sha256(os.fsencode(Path(r['root']).resolve())).hexdigest()[:12]
        assert r['compose'] == f'kineticloop-kl029-shadow-{TESTED[:7]}-{token}'
        assert r['database'] == f'kineticloop_kl029_shadow_{TESTED[:7]}_{token}'
        assert r['migration'] == 'e8c2f1a6b904'
    elif r['kind'] == 'full_TEST_owner_trajectory':
        state = r['immutable_history']
        assert len(state['authorization_issuances']) == len(state['execution_bindings']) == 2
        assert len(r['T6']['members']) == 2
        assert [b[0]['binding_kind'] for b in state['execution_bindings']].count('START') == 1
        assert [b[0]['binding_kind'] for b in state['execution_bindings']].count('RESUME') == 1
        assert state['planning_intents'][0][0]['status'] == 'FOUND_VALID_PLAN'
        bindings = {b[0]['id']: b[0] for b in state['execution_bindings']}
        assert r['START']['binding_id'] == r['CONTINUE']['binding_id']
        assert r['START']['binding_id'] in bindings and r['RESUME']['binding_id'] in bindings
        assert bindings[r['START']['binding_id']]['ref_s42_id'] == r['START']['authorization_id']
        prescriptions = {x[0]['id']: x[0] for x in state['prescription_revisions']}
        issuances = {x[0]['id']: x[0] for x in state['authorization_issuances']}
        members = {x[0]['ref_s40_id']: x[0] for x in state['bundle_prescription_members']}
        for order, result in enumerate(r['T6']['members'], 1):
            action = 'TRAINING' if order == 1 else 'NUTRITION'
            p = prescriptions[result['prescription_id']]
            a = issuances[result['authorization_id']]
            m = members[p['id']]
            assert p['prescription_kind'] == m['member_kind'] == action
            assert m['member_order'] == order and m['session_slot'] == action + '_1'
            assert digest(p['typed_payload']) == p['content_hash'] == a['bound_content_hash'] == result['content_hash']
            assert a['scope'] == 'TEST_ONLY'
            assert a['ref_s36_id'] == result['resolution_id']
            assert a['ref_s37_id'] == r['sources']['validation']['id']
            certificate = a['validity_certificate']
            assert digest(certificate['dependencies']) == certificate['closure_digest'] == r['T6']['artifact_dependency_closure_hash']
            assert {d['identity'] for d in certificate['dependencies'] if d['dependency_kind'] == 'EVIDENCE_RESOLUTION'} == {r['sources'][k]['id'] for k in ('resolution', 'nutrition_resolution')}
        for operation in ('T6', 'START', 'CONTINUE', 'PAUSE', 'RESUME'):
            result = r[operation]
            receipts = [x[0] for x in state['command_receipts'] if x[0]['id'] == result['receipt_id']]
            events = [x[0] for x in state['domain_events'] if x[0]['id'] == result['event_id']]
            assert len(receipts) == len(events) == 1 and events[0]['ref_s02_id'] == receipts[0]['id']
            assert len([x for x in state['outbox_deliveries'] if x[0]['ref_s03_id'] == events[0]['id']]) == 1

reaches = collections.Counter(r['guard_reached'] for r in rows if 'guard_reached' in r)
assert reaches['strict_owner_ingress'] == 10 and reaches['registration_guard'] == 3
assert reaches['require_wire'] == 5 and reaches['owner_current_bundle_pre_T7'] == 1
assert reaches['DB_storage_namespace'] == 7
fixture_counts = collections.Counter(r['kind'] for r in fixtures)
assert fixture_counts['sealed_source_and_published_basis'] == 4
assert fixture_counts['full_prepared_chain'] == 4
assert fixture_counts['runtime_registration'] == 4
report = {'reviewed_head_sha': REVIEWED, 'tested_commit': TESTED, 'implementation_bytes_unchanged_since_tests': True, 'scope_and_frozen_authority_unchanged': True, 'prerequisites': prerequisites, 'checks': checks, 'combined_suite_witness_counts': counts, 'guard_reach_counts': reaches, 'merged_recipe_witness_counts': fixture_counts, 'db_rerun': 'Not performed by PROTOCOL reviewer; DB_CONCURRENCY owns exclusive lifecycle.', 'result': 'PASS'}
(Path(__file__).parent / 'audit.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
