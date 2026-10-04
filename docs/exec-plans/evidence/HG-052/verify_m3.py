"""Use authoritative semantic validators for all integrations and M3."""
import argparse
import json
from build_closure import ROOT, context, schemas, v

p = argparse.ArgumentParser(); p.add_argument('--revision', required=True)
a = p.parse_args(); revision = v.resolve(ROOT, a.revision)
assert v.resolve(ROOT, 'HEAD') == revision
assert not v.git(ROOT, 'status', '--porcelain', '--untracked-files=all').strip()
backlog, tasks, records = context(revision)
s = schemas(); errors = []
closure, source_errors = v.m3_load_closure_record(ROOT, ROOT / 'docs/exec-plans/milestones/M3.json')
errors.extend(source_errors)
if closure:
    errors.extend(v.m3_milestone_closure_errors(ROOT, closure, *s, backlog, tasks))
budget = v.compact_evidence.audit(ROOT, '7d2322707b1ffe177c958ef9385ce40bb66d1e43', revision, 'HG-052')
errors.extend(budget['errors'])
report = dict(tested_commit=revision, integrations=len(records), m3_members=len(v.M3_TASK_IDS), exits=len(v.M3_EXIT_TASK_CHECKS), fresh_commands=len(v.M3_REGRESSION_COMMANDS), errors=sorted(set(errors)), budget=budget,
    production_auto_activation=False, shadow_executable=False, product_requirement_pass_claims=[],
    deferred_boundaries=12, i04_wf='NOT_RUN', shadow_usability='NOT_RUN', r04_e2e='NOT_RUN')
print(json.dumps(report, indent=2))
raise SystemExit(bool(errors))
