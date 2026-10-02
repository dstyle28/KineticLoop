"""Adversarial integer-exit probe with synthetic inputs and real read-only ancestry."""
import hashlib
import importlib.util
import json
from pathlib import Path

root = Path(__file__).resolve().parents[5]
out = Path(__file__).parent
reviewed = '19dc5a4f8edc8869873a76a4fe27b0280761d7c9'
spec = importlib.util.spec_from_file_location('protocol_exit_probe', root / 'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
assert v.resolve(root, 'HEAD') == reviewed
records = {task: {'merge_commit': 'fa729ca4bcca0f2c2e7a2aa0601890d1356b8842'} for task in v.M3_TASK_IDS}
results = []
for value in (False, 0.0):
    payload = {'change_id': 'HG-044', 'tested_commit': '0af358014182c957eec07763aaaf9181d3e2d0c1',
               'status': 'PASS', 'commands': v.M3_REGRESSION_COMMANDS,
               'executions': [{'command': c, 'tested_commit': '0af358014182c957eec07763aaaf9181d3e2d0c1',
                               'exit_code': value if i == 0 else 0} for i,c in enumerate(v.M3_REGRESSION_COMMANDS)]}
    errors = v.m3_execution_evidence_errors(root, payload, reviewed, reviewed, records)
    assert errors == ['milestone-m3-regression:failed-or-unbound-command'], errors
    results.append({'synthetic_exit_value': value, 'python_type': type(value).__name__,
                    'errors': errors})
(out / 'strict-exit-probe.json').write_text(json.dumps({'reviewed_head_sha': reviewed,
    'status': 'PASS', 'exit_code': 0, 'synthetic_data_only': True,
    'validator_sha256': hashlib.sha256((root / 'tools/harness/validate_harness.py').read_bytes()).hexdigest(),
    'results': results}, indent=2) + '\n')
print('PROTOCOL_R3_STRICT_EXIT_PASS: bool and float zero rejected at exit-code oracle')
