"""Exercise both actual governance validate branches at the reviewed SHA."""
import argparse
import importlib.util
import json
from pathlib import Path

root = Path.cwd()
out = root / 'docs/exec-plans/reviews/HG-044/PROTOCOL-r6-raw'
base = '2c44f456a0daf8e6933f20fc3eadc7e1869d6fff'
head = 'cf0b99359d04c136d01fd4c5eeec8a23cd0bbc54'
spec = importlib.util.spec_from_file_location('gate_validator', root / 'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
results = []
original = v.m3_governance_plan_prefix_errors
calls = []
def observed(root, base, reviewed):
    errors = original(root, base, reviewed)
    calls.append(dict(base=base, reviewed=reviewed, errors=errors))
    return errors
v.m3_governance_plan_prefix_errors = observed
for review_only in (False, True):
    # review-only supplies a post-integration review-dir-only diff; its original
    # governance change is replayed from the record's protected base. No commits
    # or temporary result/review substitutions are needed to exercise that branch.
    args = argparse.Namespace(protected_base=head if review_only else base,
        reviewed_head=None, task_id=None, ci_pr_base=None, ci_pr_head=None,
        governance_change_id='HG-044', governance_reviewed_head=head,
        governance_review_only=review_only)
    start = len(calls)
    errors, count, active = v.validate(root, args)
    assert len(calls) == start + 1 and calls[-1] == dict(base=base, reviewed=head, errors=[])
    assert not any('validation-error:' in e or 'governance-hg044-plan-prefix' in e for e in errors)
    results.append(dict(mode='review-only' if review_only else 'ordinary',
        errors=errors, task_count=count, active_count=active,
        committed_plan_prefix_call=calls[-1],
        scope='branch execution probe, not merge PASS; concurrent review files make the tree dirty'))
(out / 'gate-probe.json').write_text(json.dumps(results, indent=2) + '\n')
print('Both governance PR modes execute committed plan prefix guard without exception: PASS')
