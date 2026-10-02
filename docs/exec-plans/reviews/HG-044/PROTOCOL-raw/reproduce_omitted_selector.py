"""Synthetic Git regression input proving omitted-selector acceptance, not task evidence."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('validator', ROOT / 'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
repo = Path(tempfile.mkdtemp(prefix='hg044-protocol-omission-', dir='/private/tmp'))
def git(*args):
    return subprocess.check_output(['git', '-c', 'user.name=Protocol Review Fixture',
        '-c', 'user.email=review@example.invalid', '-c', 'commit.gpgsign=false',
        '-c', 'core.hooksPath=/dev/null', *args], cwd=repo,
        env=dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)).decode().strip()
git('init', '-q')
(repo/'synthetic-marker').write_text('No project completion or real DB evidence\n')
git('add', '.')
git('commit', '-qm', 'synthetic tested source')
tested = git('rev-parse', 'HEAD')
prefix = 'docs/exec-plans/evidence/HG-999/'
def raw(name, content):
    path = prefix + name
    target = repo/path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return {'path': path, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}
payload = {'change_id':'HG-999', 'tested_commit':tested, 'status':'PASS',
           'commands':v.M3_REGRESSION_COMMANDS, 'executions':[]}
omissions = []
for index, command in enumerate(v.M3_REGRESSION_COMMANDS):
    run = {'command':command, 'tested_commit':tested, 'exit_code':0}
    if command == 'uv run kl check-harness':
        run['stdout'] = raw(f'{index}.log', 'HARNESS_CHECK_PASS\n')
    else:
        selectors = (['tests/unit'] if command == 'uv run kl test-unit' else
                     ['tests/harness'] if command == 'uv run kl test-harness' else
                     command.removeprefix('uv run pytest -q ').split())
        # Deliberately supply zero cases for every selector after the first.
        node = selectors[0]
        if node in ('tests/unit', 'tests/harness'):
            node += '/example.py::test_example'
        elif '::' not in node:
            node += '::test_example'
        parts = node.split('::')
        classname = '.'.join([parts[0].removesuffix('.py').replace('/','.'), *parts[1:-1]])
        run['stdout'] = raw(f'{index}.log', '1 passed in 0.1s\n')
        run['junit'] = raw(f'{index}.xml', f'<testsuite><testcase classname="{classname}" name="{parts[-1]}"/></testsuite>')
        collection = {'command':'uv run pytest --collect-only -q ' + ' '.join(selectors),
                      'tested_commit':tested, 'exit_code':0, 'nodeids':[node],
                      'stdout':raw(f'{index}-collect.log', node + '\n1 test collected in 0.1s\n')}
        run['collection'] = raw(f'{index}-collect.json', json.dumps(collection))
        if len(selectors) > 1:
            omissions.append({'command':command, 'recorded_nodeids':[node], 'omitted_selectors':selectors[1:]})
    payload['executions'].append(run)
git('add', '.')
git('commit', '-qm', 'synthetic evidence with deliberately omitted selectors')
evaluated = git('rev-parse', 'HEAD')
records = {name:{'merge_commit':tested} for name in v.M3_TASK_IDS}
errors = v.m3_execution_evidence_errors(repo, payload, evaluated, evaluated, records)
assert omissions and errors == [], (omissions, errors)
report = {'reviewed_head_sha':'351f0eda41ad492e66115f9ea1e41e3e0f9abf3d',
          'synthetic_input_only':True, 'validator_errors':errors,
          'finding':'Multi-selector regression commands accept evidence with omitted requested files',
          'omissions':omissions, 'synthetic_git_repo':str(repo),
          'synthetic_tested_commit':tested, 'synthetic_evaluated_commit':evaluated}
(OUT/'omitted-selector-reproduction.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report, indent=2))
