import hashlib
import importlib.util
import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).parent
spec = importlib.util.spec_from_file_location('sec_integer_guard', ROOT / 'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
results = []
with tempfile.TemporaryDirectory(prefix='hg44-s6-int-', dir='/private/tmp') as temp:
    root = Path(temp)
    def git(*args):
        return subprocess.check_output(['git', '-c', 'user.name=HG044 Security Fixture', '-c', 'user.email=test@example.invalid', '-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=/dev/null', *args], cwd=root, env=dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)).decode().strip()
    git('init', '-q')
    (root / 'fixture').write_text('isolated synthetic validator inputs\n')
    git('add', '.')
    git('commit', '-qm', 'fixture tested revision')
    tested = git('rev-parse', 'HEAD')
    records = {name: {'merge_commit': tested} for name in v.M3_TASK_IDS}
    def raw(name, text):
        path = 'docs/exec-plans/evidence/HG-999/' + name
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        return {'path': path, 'sha256': hashlib.sha256(text.encode()).hexdigest()}
    output = raw('run.log', '1 passed in 0.1s\n')
    junit = raw('run.xml', '<testsuite><testcase classname="tests.unit.test_probe" name="test_case"/></testsuite>')
    collected = raw('collect.log', 'tests/unit/test_probe.py::test_case\n1 test collected in 0.1s\n')
    for field in ('run', 'collection'):
        for value in (False, 0.0):
            collection = raw('collection-' + field + '-' + type(value).__name__ + '.json', json.dumps({'command': 'uv run pytest --collect-only -q tests/unit', 'tested_commit': tested, 'exit_code': value if field == 'collection' else 0, 'nodeids': ['tests/unit/test_probe.py::test_case'], 'stdout': collected}))
            git('add', '.')
            git('commit', '--allow-empty', '-qm', 'append synthetic numeric oracle')
            evaluated = git('rev-parse', 'HEAD')
            runs = [{'command': command, 'tested_commit': tested, 'exit_code': 0, 'stdout': output, 'junit': junit, 'collection': collection} for command in v.M3_REGRESSION_COMMANDS]
            if field == 'run':
                runs[0]['exit_code'] = value
            payload = {'change_id': 'HG-999', 'tested_commit': tested, 'status': 'PASS', 'commands': v.M3_REGRESSION_COMMANDS, 'executions': runs}
            errors = v.m3_execution_evidence_errors(root, payload, evaluated, evaluated, records)
            expected = 'milestone-m3-regression:' + ('failed-or-unbound-command' if field == 'run' else 'collection-binding')
            assert errors == [expected], errors
            results.append({'field': field, 'type': type(value).__name__, 'errors': errors, 'tested_commit': tested, 'evaluated_commit': evaluated})
(OUT / 'integer-probe.json').write_text(json.dumps(results, indent=2) + '\n')
print(json.dumps(results))
