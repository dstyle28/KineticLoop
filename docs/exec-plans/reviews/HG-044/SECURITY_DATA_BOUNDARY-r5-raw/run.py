"""Retain exact bytes from bounded independent security evidence probes."""
import hashlib
import json
import os
import subprocess
from pathlib import Path

root = Path.cwd()
out = root / 'docs/exec-plans/reviews/HG-044/SECURITY_DATA_BOUNDARY-r5-raw'
python = '/private/tmp/hg044-venv/bin/python'
command = [python, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
           'tests/harness/test_m3_milestone_closure.py::test_genuine_pytest_parameter_collection_and_junit_are_accepted',
           'tests/harness/test_m3_milestone_closure.py::test_each_multiselect_suite_requires_collected_and_executed_cases',
           'tests/harness/test_m3_milestone_closure.py::test_integrated_regression_fails_closed',
           'tests/harness/test_m3_milestone_closure.py::test_m3_symlink_is_rejected_before_target_parsing',
           'tests/harness/test_m3_milestone_closure.py::test_m3_reader_parses_checked_git_blob_not_second_ambient_read',
           '--junitxml', str(out / 'bounded-probes.xml')]
env = dict(os.environ, PYTHONPATH='src', PYTHONDONTWRITEBYTECODE='1')
run = subprocess.run(command, cwd=root, env=env, capture_output=True)
stdout, stderr = out / 'bounded-probes.stdout', out / 'bounded-probes.stderr'
stdout.write_bytes(run.stdout)
stderr.write_bytes(run.stderr)
record = dict(reviewed_head_sha='027bc2368e36e28aa9956489cb57af297882d671', command=command,
              exit_code=run.returncode, stdout_sha256=hashlib.sha256(run.stdout).hexdigest(),
              stderr_sha256=hashlib.sha256(run.stderr).hexdigest(), stdout_bytes=len(run.stdout),
              stderr_bytes=len(run.stderr))
(out / 'bounded-probes.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record))
raise SystemExit(run.returncode)
