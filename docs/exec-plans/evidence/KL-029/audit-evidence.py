"""Inspect raw witnesses rather than inferring isolation from pytest's exit status."""
import collections
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[4]
log = root / 'docs/exec-plans/evidence/KL-029/checks-b9fbf9b/shadow_suite_dc.log'
records = [json.loads(line.removeprefix('SHADOW_EVIDENCE ')) for line in log.read_text().splitlines() if line.startswith('SHADOW_EVIDENCE ')]
counts = collections.Counter(r['kind'] for r in records)
assert counts['full_TEST_owner_trajectory'] == 4
assert counts['actual_T7_positive_guard'] == 12
assert counts['cleanup'] == 4
assert counts['live_privilege_denial'] == 15
assert counts['zero_effect'] == 26
assert counts['declared_external_evaluation_inputs'] == 3
for record in records:
    assert record['tested_commit'] == 'b9fbf9b475e07765db62e67f0104a800036dda4d'
    if record['kind'] == 'zero_effect':
        assert record['before'] == record['after'] and record['zero_new_receipt_event_outbox']
    if record['kind'] == 'cleanup':
        assert not any(record['remaining'].values())
    if record['kind'] == 'actual_T7_positive_guard':
        assert record['decision']['is_executable'] and record['decision']['non_bearer']
    if record['kind'] == 'scope_denial':
        assert record['code'] == 'SUBJECT_SCOPE_DENIED'
        assert record['response'] == {'error':'subject_scope_denied'}
        assert record['timing_class'] == 'BOUNDED_SCOPE_LOOKUP' and not record['measured_constant_time']
summary = {'tested_commit':'b9fbf9b475e07765db62e67f0104a800036dda4d', 'raw_log':str(log.relative_to(root)), 'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(), 'witness_counts':dict(counts), 'guard_reach_counts':dict(collections.Counter(r['guard_reached'] for r in records if 'guard_reached' in r)), 'full_history_equalities':26, 'cleanup_empty':4, 'external_archives_not_shadow_API':True, 'product_pass_claims':[]}
(root/'docs/exec-plans/evidence/KL-029/checks-b9fbf9b/oracle-audit.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
