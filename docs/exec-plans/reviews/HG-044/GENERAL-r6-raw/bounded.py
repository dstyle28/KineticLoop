"""Run only review-relevant focused cases; preserve subprocess bytes."""
import hashlib
import json
import os
import subprocess
from pathlib import Path

root = Path.cwd()
out = root / 'docs/exec-plans/reviews/HG-044/GENERAL-r6-raw'
module = 'tests/harness/test_m3_milestone_closure.py'
cases = ['test_hg044_plan_prefix_reads_committed_reviewed_revision',
         'test_each_multiselect_suite_requires_collected_and_executed_cases',
         'test_genuine_pytest_parameter_collection_and_junit_are_accepted',
         'test_integrated_regression_fails_closed[float-exit]',
         'test_integrated_regression_fails_closed[collection-float-exit]',
         'test_integrated_regression_fails_closed[collection-type]',
         'test_integrated_regression_fails_closed[collection-skipped]',
         'test_integrated_regression_fails_closed[wrong-selector]',
         'test_legacy_m1_m2_schema_and_validator_behavior_unchanged',
         'test_existing_schema_branches_preserved',
         'test_governance_scope_excludes_peer_and_runtime_and_closure_instance',
         'test_ratified_plan_mapping_guard_preserves_addendum']
command = ['/private/tmp/hg044-venv/bin/python','-m','pytest','-q','-p','no:cacheprovider',
           '--basetemp','/private/tmp/hg044-gr6','--junitxml',str(out/'bounded.xml'),
           *(module+'::'+case for case in cases)]
env = dict(os.environ, PYTHONPATH=str(root/'src'),PYTHONDONTWRITEBYTECODE='1',TMPDIR='/private/tmp')
run = subprocess.run(command,cwd=root,env=env,capture_output=True)
(out/'bounded.stdout').write_bytes(run.stdout)
(out/'bounded.stderr').write_bytes(run.stderr)
(out/'bounded.json').write_text(json.dumps(dict(command=command,exit_code=run.returncode,
    stdout_sha256=hashlib.sha256(run.stdout).hexdigest(),stderr_sha256=hashlib.sha256(run.stderr).hexdigest()),indent=2)+'\n')
print(run.stdout.decode(),end='')
raise SystemExit(run.returncode)
