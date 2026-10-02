"""Persist only this task's exact-SHA protocol review after independent checks pass."""
import hashlib
import json
import os
import subprocess
from pathlib import Path

import jsonschema

root = Path(__file__).resolve().parents[5]
out = Path(__file__).parent
reviewed = '19dc5a4f8edc8869873a76a4fe27b0280761d7c9'
assert subprocess.check_output(['git','rev-parse','HEAD'], cwd=root).decode().strip() == reviewed
env = dict(os.environ, PYTHONPATH=str(root / 'src'), PYTHONDONTWRITEBYTECODE='1')
captures = []
for name in ('ancestry', 'strict-exit-probe', 'collection-probe'):
    argv = ['/private/tmp/hg044-venv/bin/python', str(out / (name + '.py'))]
    run = subprocess.run(argv, cwd=root, env=env, capture_output=True)
    raw = run.stdout + run.stderr
    path = out / (name + '.log')
    path.write_bytes(raw)
    captures.append({'argv': argv, 'reviewed_head_sha': reviewed, 'exit_code': run.returncode,
                     'raw_path': str(path.relative_to(root)), 'raw_byte_count': len(raw),
                     'raw_sha256': hashlib.sha256(raw).hexdigest()})
    assert run.returncode == 0, raw.decode()
(out / 'supplemental-commands.json').write_text(json.dumps(captures, indent=2) + '\n')
commands = json.loads((out / 'commands.json').read_text())
assert commands['reviewed_head_sha'] == reviewed
assert len(commands['commands']) == 3 and all(c['exit_code'] == 0 for c in commands['commands'])
for command in commands['commands'] + captures:
    raw = (root / command['raw_path']).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == command['raw_sha256']
    assert len(raw) == command['raw_byte_count']
for name in ('audit', 'ancestry', 'strict-exit-probe'):
    payload = json.loads((out / (name + '.json')).read_text())
    assert payload['reviewed_head_sha'] == reviewed and payload['status'] == 'PASS'
test_log = (out / 'command-1.log').read_text()
assert 'passed' in test_log and 'failed' not in test_log
refs = [str(p.relative_to(root)) for p in sorted(out.iterdir()) if p.is_file()]
findings = [
    {'finding_id': 'HG044-PROTOCOL-R3-001', 'severity': 'BLOCKER', 'priority': 1,
     'title': 'Preserve parameter suffixes when matching pytest JUnit names',
     'file': 'tools/harness/validate_harness.py', 'start': 2650, 'end': 2655,
     'body': "Required full-harness evidence contains 25 current parameter IDs with '::' inside brackets. Pytest partitions the parameter suffix before splitting the address, but this validator splits the entire node. A valid tests/harness/test_probe.py::test_valid[selector::case] collection and official pytest JUnit name is rejected as incomplete-executed-collection. The same error affects the current full-harness suite, so valid fresh mandatory regression cannot close M3. Partition '[' first, split only the address, and restore the full parameter suffix to the final test name using pytest-compatible semantics; add both class-based and parameter-delimiter positive evidence tests and rerun at a new implementation SHA.",
     'evidence_refs': ['docs/exec-plans/reviews/HG-044/PROTOCOL-r3-raw/collection-probe.py',
                       'docs/exec-plans/reviews/HG-044/PROTOCOL-r3-raw/collection-probe.json']},
    {'finding_id': 'HG044-PROTOCOL-R3-002', 'severity': 'BLOCKER', 'priority': 1,
     'title': 'Do not interpret collected node parameter text as a skip summary',
     'file': 'tools/harness/validate_harness.py', 'start': 2645, 'end': 2646,
     'body': "The disposition regex searches the entire raw collection output, including node records. Three current HG044 harness cases legitimately have parameter IDs containing '1 skipped' or '1 error'; successful collection of these nodes has integer zero exit and no skipped/error disposition. A valid collected/executed case named test_zero_skip_xfail_failure_cannot_supply_oracle[1 skipped] is rejected as collection-oracle. Thus required full-harness regression cannot validate even after the JUnit delimiter fix. Exclude node record lines before checking disposition summaries and keep strict rejection of genuine skipped/error/deselected summary records; add a positive parameter-text case and genuine negative summary cases at a new reviewed SHA.",
     'evidence_refs': ['docs/exec-plans/reviews/HG-044/PROTOCOL-r3-raw/collection-probe.py',
                       'docs/exec-plans/reviews/HG-044/PROTOCOL-r3-raw/collection-probe.json']},
]
review = {'task_identity': 'harness-governance-v0.1/HG-044', 'reviewed_head_sha': reviewed,
          'review_type': 'PROTOCOL', 'status': 'CHANGES_REQUIRED', 'findings': findings,
          'review_contract_version': 'v0.2', 'evidence_refs': refs}
jsonschema.Draft202012Validator(json.loads((root / 'THREAD_REVIEW.schema.json').read_text())).validate(review)
(out.parent / 'PROTOCOL.json').write_text(json.dumps(review, indent=2) + '\n')
print('PROTOCOL_R3_CHANGES_REQUIRED ' + reviewed + '\n' + test_log)
