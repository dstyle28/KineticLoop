"""Exercise real validate branches and real Git prefix reads in both PR modes."""
import argparse
import importlib.util
import json
from pathlib import Path

root = Path.cwd()
out = root / 'docs/exec-plans/reviews/HG-044/GENERAL-r6-raw'
base = '2c44f456a0daf8e6933f20fc3eadc7e1869d6fff'
reviewed = 'cf0b99359d04c136d01fd4c5eeec8a23cd0bbc54'
spec = importlib.util.spec_from_file_location('general_r6_gate',root/'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
original = v.m3_governance_plan_prefix_errors
calls = []
def observed(root_arg, base_arg, reviewed_arg):
    errors = original(root_arg,base_arg,reviewed_arg)
    calls.append(dict(base=base_arg,reviewed=reviewed_arg,errors=errors))
    return errors
v.m3_governance_plan_prefix_errors = observed
configured = argparse.Namespace(ci_pr_base=base,ci_pr_head=reviewed,task_id=None,
                                reviewed_head=None,protected_base=None)
v.configure_ci_merge_gate(root,configured)
assert configured.governance_change_id == 'HG-044'
assert not getattr(configured,'governance_review_only',False)
results = []
for review_only in (False,True):
    args = argparse.Namespace(protected_base=reviewed if review_only else base,
        task_id=None,reviewed_head=None,governance_change_id='HG-044',
        governance_reviewed_head=reviewed,governance_review_only=review_only)
    before = len(calls)
    errors,count,active = v.validate(root,args)
    assert len(calls) == before+1
    assert calls[-1] == dict(base=base,reviewed=reviewed,errors=[])
    assert not any('governance-hg044-plan-prefix' in e or 'validation-error:' in e for e in errors)
    results.append(dict(mode='review-only' if review_only else 'normal',
        protected_base=args.protected_base,observed_guard_call=calls[-1],
        diagnostics=errors,task_count=count,active_count=active))
(out/'gate-wiring.json').write_text(json.dumps(dict(status='PASS',
    normal_ci_discovery=dict(change_id=configured.governance_change_id,
        reviewed=configured.governance_reviewed_head,
        note='Existing historical GENERAL review supplies its historical SHA until fresh review persistence.'),
    branches=results,note='Direct validate calls select the exact r6 reviewed SHA; all real committed plan reads and branch bodies run. Review-only CI discovery is unchanged byte-identical baseline code.'),indent=2)+'\n')
print('PASS: both validate branches call the real committed prefix guard with base and reviewed SHA.')
