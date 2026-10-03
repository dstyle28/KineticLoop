"""Read only exact Git revisions and lossless compact evidence; no live services."""
import collections
import hashlib
import importlib.util
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[5]
BASE = '034d6301316d0dade784a61b159c027b83fbce3a'
TESTED = 'f302b22c0838ef2928913392e7c2a6af9e8f8698'
REVIEWED = '26482f7f7147fe33cf37d8028574196c97c82ec6'
PREFIX = 'docs/exec-plans/evidence/HG-050/runs/'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def at(path):
    return git('show', REVIEWED + ':' + path)


def main():
    git('merge-base', '--is-ancestor', BASE, TESTED)
    git('merge-base', '--is-ancestor', TESTED, REVIEWED)
    record = yaml.safe_load(at('docs/exec-plans/governance/HG-050.yaml'))
    assert record['change_identity'] == 'harness-governance-v0.1/HG-050'
    assert record['base_commit'] == BASE and record['tested_commit'] == TESTED
    assert record['packets_refined'] == [] and record['frozen_impact'] == 'NONE'
    changed = git('diff', '--name-only', BASE, REVIEWED).decode().splitlines()
    assert sorted(changed) == sorted(record['files_changed'])
    exact = {'CURRENT_DOCUMENT_INDEX.json', 'HARNESS_DOCUMENT_MANIFEST.json',
             'tools/harness/github_app.py', 'tests/harness/test_local_gate.py',
             'tools/harness/validate_harness.py', 'docs/harness/LOCAL_DB_CI.md',
             'docs/exec-plans/governance/HG-050.yaml'}
    assert all(p in exact or p.startswith('docs/exec-plans/evidence/HG-050/') for p in changed)
    suffix = git('diff', '--name-only', TESTED, REVIEWED).decode().splitlines()
    assert all(p in {'CURRENT_DOCUMENT_INDEX.json', 'HARNESS_DOCUMENT_MANIFEST.json',
                     'docs/exec-plans/governance/HG-050.yaml'}
               or p.startswith('docs/exec-plans/evidence/HG-050/') for p in suffix)
    for p in ['tools/harness/github_app.py', 'tools/harness/validate_harness.py',
              'tests/harness/test_local_gate.py', 'docs/harness/LOCAL_DB_CI.md']:
        assert at(p) == git('show', TESTED + ':' + p)
    # Import only the unchanged, byte-matched trusted decoder from this reviewed tree.
    decoder = ROOT / 'tools/harness/compact_evidence.py'
    assert decoder.read_bytes() == at('tools/harness/compact_evidence.py')
    spec = importlib.util.spec_from_file_location('hg050_review_decoder', decoder)
    ce = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ce)
    recovered = {}
    paths = git('ls-tree', '-r', '--name-only', REVIEWED, '--', PREFIX).decode().splitlines()
    for p in paths:
        if p.endswith('.json'):
            envelope = json.loads(at(p))
            if envelope.get('kineticloop_evidence') == 'gzip-v1':
                recovered[p] = ce.read(ROOT, p, REVIEWED, tested=TESTED)
    for check in record['checks_run']:
        p = check['evidence_ref']
        assert check['result'] == 'PASS'
        ce.read(ROOT, p, REVIEWED, tested=TESTED, command=check['command'], exit_code=0)
    runs = {}
    for name in ['initial-failed', 'retry-failed', 'isolated-pass']:
        def raw(artifact):
            return recovered[PREFIX + name + '-harness-' + artifact + '.json']
        manifest = json.loads(raw('manifest-json'))
        execution = json.loads(raw('execution-json'))
        collection = json.loads(raw('collection-json'))
        junit = ET.fromstring(raw('junit-xml'))
        cases = list(junit.iter('testcase'))
        assert manifest['tested_commit'] == TESTED and manifest['dirty_source'] is False
        for file in manifest['files']:
            artifact = {'collection.json': 'collection-json', 'collection.log': 'collection-log',
                        'execution.json': 'execution-json', 'junit.xml': 'junit-xml',
                        'pytest.log': 'pytest-log'}[file['path']]
            payload = raw(artifact)
            assert file['bytes'] == len(payload)
            assert file['sha256'] == hashlib.sha256(payload).hexdigest()
        problems = sum(len(list(c.iter(tag))) for c in cases
                       for tag in ['skipped', 'error', 'failure'])
        calls = [r for r in execution['reports'] if r['phase'] == 'call']
        counts = dict(collections.Counter(r['outcome'] for r in calls))
        runs[name] = {'wrapper_exit': manifest['exit_code'],
                      'pytest_exit': manifest['pytest_exit_code'],
                      'execution_complete': manifest['execution_complete'],
                      'junit_cases': len(cases), 'junit_problems': problems,
                      'call_outcomes': counts, 'manifest_errors': manifest['errors']}
        if name == 'isolated-pass':
            assert manifest['exit_code'] == manifest['pytest_exit_code'] == 0
            assert manifest['execution_complete'] is True and manifest['errors'] == []
            assert execution['exit_code'] == 0 and execution['errors'] == []
            assert collection['exit_code'] == 0 and collection['errors'] == []
            nodes = collection['collections']['serial']
            assert len(nodes) == len(set(nodes)) == 1405
            assert len(cases) == 1405 and problems == 0 and counts == {'passed': 1405}
            assert len(execution['started']) == 1405 and set(execution['started']) == set(nodes)
            assert set(execution['collections']) == {'gw0', 'gw1'}
            assert all(v == nodes for v in execution['collections'].values())
            assert len(execution['reports']) == 4215
            assert all(r['outcome'] == 'passed' for r in execution['reports'])
            phases = collections.Counter((r['nodeid'], r['phase']) for r in execution['reports'])
            assert all(phases[n, phase] == 1 for n in nodes for phase in ['setup', 'call', 'teardown'])
            assert b'1405 passed' in raw('pytest-log')
        else:
            assert manifest['exit_code'] == 1 and manifest['execution_complete'] is False
    assert runs['initial-failed']['call_outcomes'] == {'passed': 1405}
    assert runs['retry-failed']['junit_problems'] == 1
    focused = recovered[PREFIX + 'focused.json']
    unit = recovered[PREFIX + 'unit.json']
    assert b'102 passed' in focused and b'241 passed' in unit
    print(json.dumps({'status': 'PASS', 'reviewed_sha': REVIEWED, 'tested_sha': TESTED,
                      'base_sha': BASE, 'scope_paths': len(changed),
                      'decoded_envelopes': len(recovered), 'runs': runs,
                      'focused': 102, 'unit': 241,
                      'installation_controller_database_product_m3_release': 'NOT_RUN'}, indent=2))


if __name__ == '__main__':
    main()
