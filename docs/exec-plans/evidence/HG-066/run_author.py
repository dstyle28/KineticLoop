"""One fresh stable-T author cycle, actual subprocess exits and positive identities."""
import argparse
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter
from _pytest.junitxml import mangle_test_address
from pathlib import Path
E = Path(__file__).resolve().parent
R = E.parents[3]
B = '3768c1b4366677934cb952ef808343edcee4e438'
CACHE = ['/Users/davetian/.cache/uv/archive-v0/nnPNXkWpFSNRe9Ad', '/Users/davetian/.cache/uv/archive-v0/X_H5kIMi_L692EPn']

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def identity(observer, junit, collection=None):
    data = json.loads(observer.read_bytes())
    collections = list(data['collections'].values())
    ids = collections[0]
    assert ids and len(ids) == len(set(ids)) and all(i == ids for i in collections)
    assert Counter(data['started']) == Counter(ids) and not data['errors'] and data['exit_code'] == 0
    if collection:
        c = json.loads(collection.read_bytes())
        assert c['exit_code'] == 0 and not c['errors'] and not c['started'] and not c['reports']
        assert list(c['collections'].values()) == [ids]
    for phase in ('setup', 'call', 'teardown'):
        reports = [r for r in data['reports'] if r['phase'] == phase]
        assert Counter(r['nodeid'] for r in reports) == Counter(ids)
        assert all(r['outcome'] == 'passed' for r in reports)
    tree = ET.parse(junit).getroot()
    cases = list(tree.iter('testcase'))
    assert len(cases) == len(ids)
    assert not any(list(tree.iter(tag)) for tag in ('failure', 'error', 'skipped'))
    pairs = []
    for node in ids:
        parts = mangle_test_address(node)
        pairs.append(('.'.join(parts[:-1]), parts[-1]))
    assert Counter((c.get('classname'), c.get('name')) for c in cases) == Counter(pairs)
    return {'identities': ids, 'cases': len(ids), 'phases': len(ids) * 3, 'positive_collection_start_execution_phase_junit_equal': True}

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--tested', required=True)
    args = p.parse_args()
    T = args.tested
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=R, text=True).strip() == T
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=R)
    out = Path('/private/tmp/hg066-author-' + T[:12])
    out.mkdir(exist_ok=False)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=':'.join([str(R), str(R/'src'), *CACHE]), RUFF_CACHE_DIR=str(out/'ruff-cache'), MYPY_CACHE_DIR=str(out/'mypy-cache'))
    env.pop('PYTEST_DISABLE_PLUGIN_AUTOLOAD', None)
    env.pop('PYTEST_ADDOPTS', None)
    commands = []
    identities = {}
    def run(name, argv, extra=None):
        actual = dict(env, **(extra or {}))
        start = time.monotonic_ns()
        with (out / (name + '.log')).open('wb') as output:
            proc = subprocess.run(argv, cwd=R, env=actual, stdout=output, stderr=subprocess.STDOUT)
        row = {'check_id': name, 'argv': argv, 'command': ' '.join(argv), 'cwd': str(R), 'environment': {k:v for k,v in actual.items() if k in ('PYTHONPATH','PYTHONDONTWRITEBYTECODE','PYTEST_ADDOPTS','KINETICLOOP_HARNESS_WORKERS','KINETICLOOP_HARNESS_ROOT','KINETICLOOP_HARNESS_OBSERVER','RUFF_CACHE_DIR','MYPY_CACHE_DIR')}, 'exit_code': proc.returncode, 'elapsed_ns': time.monotonic_ns()-start, 'stdout_stderr_sha256': digest((out/(name+'.log')).read_bytes())}
        commands.append(row)
        (out/'COMMANDS.json').write_text(json.dumps(commands, indent=2)+'\n')
        print(name, proc.returncode, flush=True)
        if proc.returncode:
            raise SystemExit(proc.returncode)
    run('definitions', [sys.executable, str(E/'verify_definitions.py'), '--base', B, '--tested', T])
    for name, selector, argv in [('validator','tests/harness/test_validator.py',[sys.executable,'-m','pytest','tests/harness/test_validator.py','-q']),('unit','tests/unit',[sys.executable,'-m','kineticloop.cli','test-unit'])]:
        extra = {'KINETICLOOP_HARNESS_WORKERS':'1','KINETICLOOP_HARNESS_ROOT':str(R),'KINETICLOOP_HARNESS_OBSERVER':str(out/(name+'-collection.json'))}
        run(name+'-collection', [sys.executable,'-m','pytest',selector,'--collect-only','-q','-p','tools.harness.parallel_observer','-p','no:cacheprovider'],extra)
        extra.update(KINETICLOOP_HARNESS_OBSERVER=str(out/(name+'-execution.json')), PYTEST_ADDOPTS='-p tools.harness.parallel_observer -p no:cacheprovider --junitxml='+str(out/(name+'.junit.xml')))
        run(name,argv,extra)
        identities[name] = identity(out/(name+'-execution.json'),out/(name+'.junit.xml'),out/(name+'-collection.json'))
    run('harness',[sys.executable,'-m','kineticloop.cli','test-harness','--workers','2','--evidence-dir',str(out/'harness-run')])
    for name in ('lint','typecheck'):
        run(name,[sys.executable,'-m','kineticloop.cli',name])
    run('authority',[sys.executable,'-m','kineticloop.cli','check-harness'])
    run('diff',['git','diff','--check',B,T])
    # Harness driver independently proves every worker/phase/JUnit identity;
    # this parent also retains and verifies its exact observation objects.
    h = out/'harness-run'
    identities['harness'] = identity(h/'execution.json',h/'junit.xml',h/'collection.json')
    (out/'IDENTITIES.json').write_text(json.dumps(identities,indent=2)+'\n')
    author = [row for row in commands if not row['check_id'].endswith('-collection')]
    assert len(author) == 8 and all(row['exit_code'] == 0 for row in author)
    (out/'AUTHOR_RESULT.json').write_text(json.dumps({'base': B,'tested':T,'checks':author,'identities':{k:{x:y for x,y in v.items() if x!='identities'} for k,v in identities.items()},'historical_execution':'UNVERIFIED','runtime':'NOT_RUN'},indent=2)+'\n')
    print('AUTHOR_COMPLETE',str(out),flush=True)

if __name__ == '__main__':
    main()
