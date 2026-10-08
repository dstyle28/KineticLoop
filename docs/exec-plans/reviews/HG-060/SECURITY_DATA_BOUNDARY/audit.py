"""Independent HG060 security review: immutable objects and raw execution oracles."""
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import xml.etree.ElementTree as ET

import yaml
from jsonschema import Draft202012Validator
from tools.harness import compact_evidence as ce

ROOT = Path(__file__).resolve().parents[5]
B = '6d24db615b7c6e517478530d130feecd678bc123'
T = '5c1b24369df37c11031c09badd6fe430acc60f74'
R = 'bba4a4d0341473aa9e652b423eedef5d1d1362c8'
F = '3965cac382d333bd97f6c67fec8ecbe805b5932f'
E = 'docs/exec-plans/evidence/HG-060/'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, timeout=60)


def blob(rev, path):
    line = git('ls-tree', '-l', rev, '--', path).strip()
    metadata, name = line.split(b'\t')
    mode, kind, oid, size = metadata.split()
    assert mode in (b'100644', b'100755') and kind == b'blob' and name.decode() == path
    data = git('cat-file', 'blob', oid.decode())
    assert len(data) == int(size)
    return data


def obj(rev, path):
    return json.loads(blob(rev, path))


def hash_bytes(data):
    return hashlib.sha256(data).hexdigest()


def execute():
    assert git('rev-parse', 'HEAD').decode().strip() == R
    git('merge-base', '--is-ancestor', B, T)
    git('merge-base', '--is-ancestor', T, R)
    record = yaml.safe_load(blob(R, 'docs/exec-plans/governance/HG-060.yaml'))
    Draft202012Validator(obj(R, 'HARNESS_CHANGE.schema.json')).validate(record)
    changed = git('diff', '--name-only', B, R).decode().splitlines()
    assert sorted(record['files_changed']) == sorted(changed)
    suffix = git('rev-list', '--reverse', T + '..' + R).decode().splitlines()
    assert suffix == [R]
    assert git('rev-list', '--parents', '-n', '1', R).decode().split() == [R, T]
    suffix_paths = git('diff', '--name-only', T, R).decode().splitlines()
    assert all(p.startswith(E) or p == 'docs/exec-plans/governance/HG-060.yaml'
               or p == 'HARNESS_DOCUMENT_MANIFEST.json' for p in suffix_paths)
    for p in changed:
        if not p.startswith(E) and p not in ('docs/exec-plans/governance/HG-060.yaml',
                                             'HARNESS_DOCUMENT_MANIFEST.json'):
            assert blob(T, p) == blob(R, p)
    source_before = obj(B, 'docs/harness/REVIEW_SOURCE_DECLARATIONS.json')
    source_after = obj(R, 'docs/harness/REVIEW_SOURCE_DECLARATIONS.json')
    assert source_after['declarations'][:6] == source_before['declarations']
    assert len(source_after['declarations']) == 8
    declarations = []
    for row in obj(R, E + 'SOURCE_IDENTITIES.json'):
        d = row['declaration']
        original = blob(d['original_review_record_commit'], d['review_record_path'])
        assert hash_bytes(original) == row['record']['sha256']
        review = json.loads(original)
        assert (review['task_identity'], review['review_type'], review['reviewed_head_sha']) == (
            d['owner'], d['review_type'], d['reviewed_head_sha'])
        assert d['reference'] in review['evidence_refs']
        git('merge-base', '--is-ancestor', d['reviewed_head_sha'], d['original_review_record_commit'])
        git('merge-base', '--is-ancestor', d['original_review_record_commit'], B)
        data = blob(d['reviewed_head_sha'], d['reference'])
        assert len(data) == 14776 and hash_bytes(data) == row['source']['sha256']
        source_tree = ast.parse(data)
        names = [n.name for n in ast.walk(source_tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
        assert any('review' in n for n in names)
        declarations.append({'owner': d['owner'], 'source_sha256': hash_bytes(data),
                             'source_bytes': len(data), 'source_definitions': len(names)})
    disposition = obj(R, E + 'PRESERVATION_DISPOSITION.json')
    native = []
    for entry in disposition['entries']:
        pin = entry['original']
        data = blob(F, pin['path'])
        assert len(data) == pin['bytes'] and hash_bytes(data) == pin['sha256']
        assert ce.envelope(data) is None and ce.reencoding_record(data) is None
        assert not ce.embedded_raw(json.loads(data))
        assert not git('ls-tree', R, '--', entry['destination']).strip()
        native.append({'path': pin['path'], 'bytes': len(data), 'native_classification': 'ordinary'})
    index = obj(R, E + 'checks-5c1b24369df3/CHECK_INDEX.json')
    assert record['tested_commit'] == T and record['base_commit'] == B
    assert [x['check_id'] for x in index['checks']] == [x['check_id'] for x in record['checks_run']]
    assert len(index['checks']) == 8
    decoded = {}
    for p in changed:
        if p.startswith(E) and p.endswith('.json'):
            value = obj(R, p)
            if isinstance(value, dict) and 'kineticloop_evidence' in value:
                decoded[p] = ce.read(ROOT, p, R)
    result = []
    for row, check in zip(index['checks'], record['checks_run'], strict=True):
        assert row['tested_commit'] == T and row['exit_code'] == 0 and check['result'] == 'PASS'
        assert row['command'] == shlex.join(row['argv']) == check['command']
        assert row['output_ref'] == check['evidence_ref']
        env = row['PYTHONPATH'].split(':')
        assert env[:2] == [str(ROOT), str(ROOT / 'src')]
        output = ce.read(ROOT, row['output_ref'], R, tested=T, command=row['command'], exit_code=0)
        assert output == decoded[row['output_ref']]
        result.append({'check_id': row['check_id'], 'exit_code': row['exit_code'],
                       'raw_bytes': len(output), 'raw_sha256': hash_bytes(output)})
    suites = []
    for name, count in [('validator', 164), ('unit', 247), ('harness', 1773)]:
        row = next(x for x in index['checks'] if x['check_id'] == name)
        refs = row['evidence_refs']
        collection = next(p for p in refs if p.endswith('collection.json.json'))
        execution = next(p for p in refs if p.endswith('execution.json.json'))
        junit = next(p for p in refs if p.endswith('junit.xml.json'))
        c, x = json.loads(decoded[collection]), json.loads(decoded[execution])
        assert c['exit_code'] == x['exit_code'] == 0 and not c['errors'] and not x['errors']
        collected = next(iter(c['collections'].values()))
        assert len(collected) == len(set(collected)) == count
        assert all(ids == collected for ids in x['collections'].values())
        assert Counter(x['started']) == Counter(collected)
        assert len(x['reports']) == 3 * count
        assert all(r['outcome'] == 'passed' for r in x['reports'])
        assert Counter((r['nodeid'], r['phase']) for r in x['reports']) == Counter(
            (node, phase) for node in collected for phase in ('setup', 'call', 'teardown'))
        xml = ET.fromstring(decoded[junit])
        cases = list(xml.iter('testcase'))
        assert len(cases) == count
        for suite in xml.iter('testsuite'):
            assert int(suite.attrib['tests']) == count
            assert all(int(suite.attrib[k]) == 0 for k in ('errors', 'failures', 'skipped'))
        assert not list(xml.iter('skipped')) and not list(xml.iter('failure')) and not list(xml.iter('error'))
        expected = []
        for node in collected:
            # Pytest retains separators inside parameter IDs in the testcase name.
            address, bracket, parameters = node.partition('[')
            names = address.split('::')
            names[0] = names[0].removesuffix('.py').replace('/', '.')
            names[-1] += bracket + parameters
            expected.append(('.'.join(names[:-1]), names[-1]))
        assert Counter(expected) == Counter((case.attrib['classname'], case.attrib['name']) for case in cases)
        for p in refs:
            env = obj(R, p)
            assert env['tested_commit'] == T and env['exit_code'] == 0
            command = env['command']
            if 'collection.' in p:
                expected_command = shlex.join(row.get('collection_argv') or row['harness_manifest']['collection_command'])
            elif name == 'harness' and not p.endswith('manifest.json.json'):
                expected_command = shlex.join(row['harness_manifest']['command'])
            else:
                expected_command = row['command']
            assert command == expected_command, (p, command, expected_command)
        suites.append({'suite': name, 'collected': count, 'started': count,
                       'passed_calls': count, 'phase_reports': len(x['reports']), 'junit_cases': len(cases),
                       'workers': sorted(x['collections']), 'nodeids_sha256': hash_bytes('\n'.join(collected).encode()),
                       'skips_errors_failures_worker_loss': 0})
    superseded = []
    for short in ('290d5fc262f3', 'e821c542b788'):
        state = obj(R, E + 'superseded-' + short + '/ROUND_STATE.json')
        assert state['harness'] == dict(state='INTERRUPTED', actual_cli_exit=-15, driver_exit=241,
                                       pytest_exit=None, execution_complete=False)
        assert set(state['remaining'].values()) == {'NOT_RUN'}
        for art in state['artifacts']:
            data = decoded[art['evidence_ref']]
            assert len(data) == art['bytes'] and hash_bytes(data) == art['sha256']
        partial = state['partial_child_output']
        assert blob(R, partial['path']) == decoded[next(a['evidence_ref'] for a in state['artifacts']
                                                       if a['sha256'] == partial['sha256'])]
        assert partial['command_exit_code'] is None
        superseded.append({'tested_commit': state['tested_commit'], 'harness': state['harness'],
                           'remaining': state['remaining']})
    return {'status': 'PASS', 'protected_base': B, 'tested_commit': T, 'reviewed_head': R,
            'changed_paths_count': len(changed), 'tested_result_suffix': suffix,
            'source_declarations': declarations, 'preservation_native': native,
            'decoded_envelopes': len(decoded), 'actual_check_outputs': result,
            'positive_execution': suites, 'superseded': superseded,
            'limits': 'Review checks immutable evidence only; installed/controller/DB/hosted gates remain separate.'}


if __name__ == '__main__':
    print(json.dumps(execute(), indent=2))
