import hashlib
import importlib.util
import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).parent
spec = importlib.util.spec_from_file_location('sec_result_guard', ROOT / 'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
results = []
with tempfile.TemporaryDirectory(prefix='hg44-s6-mode-', dir='/private/tmp') as temp:
    root = Path(temp)
    def git(*args):
        return subprocess.check_output(['git', '-c', 'user.name=HG044 Security Fixture', '-c', 'user.email=test@example.invalid', '-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=/dev/null', *args], cwd=root, env=dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)).decode().strip()
    git('init', '-q')
    path = root / 'docs/exec-plans/completed/KL-074_RESULT.json'
    path.parent.mkdir(parents=True)
    path.write_text('{}')
    git('add', '.')
    git('commit', '-qm', 'regular result fixture')
    revision = git('rev-parse', 'HEAD')
    records = {'KL-074': {'reviewed_head_sha': revision}}
    tasks = {'KL-074': {'depends_on': []}}
    regular = v.m3_dependency_order_errors(root, records, tasks)
    assert regular == []
    results.append({'mode': 'regular', 'revision': revision, 'errors': regular})
    path.unlink()
    path.symlink_to('../../../private.json')
    (root / 'private.json').write_text('{}')
    git('add', '.')
    git('commit', '-qm', 'nonregular reviewed result fixture')
    records['KL-074']['reviewed_head_sha'] = git('rev-parse', 'HEAD')
    errors = v.m3_dependency_order_errors(root, records, tasks)
    assert errors == ['milestone-m3-dependency-order:invalid:result-representation:KL-074']
    results.append({'mode': 'symlink', 'revision': records['KL-074']['reviewed_head_sha'], 'errors': errors})
(OUT / 'result-mode-probe.json').write_text(json.dumps(results, indent=2) + '\n')
print(json.dumps(results))
