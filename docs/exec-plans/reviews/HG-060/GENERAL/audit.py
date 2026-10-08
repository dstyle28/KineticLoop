"""Independent immutable-Git evidence and scope audit; writes no source bodies."""
import collections
import gzip
import hashlib
import json
from pathlib import Path
import shlex
import re
from tools.harness import compact_evidence as compact
import subprocess
import xml.etree.ElementTree as ET
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[5]
R = 'bba4a4d0341473aa9e652b423eedef5d1d1362c8'
B = '6d24db615b7c6e517478530d130feecd678bc123'
T = '5c1b24369df37c11031c09badd6fe430acc60f74'
OWN = 'docs/exec-plans/evidence/HG-060/'
OUT = Path(__file__).parent

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, timeout=60)

def blob(revision, path):
    meta, actual = git('ls-tree', '-l', revision, '--', path).strip().split(b'\t')
    mode, kind, oid, size = meta.split()
    assert actual.decode() == path and mode in (b'100644', b'100755') and kind == b'blob'
    data = git('cat-file', 'blob', oid.decode())
    assert len(data) == int(size)
    return data

def obj(path, revision=R):
    return json.loads(blob(revision, path))

raw_identities = {}
def decode(path):
    e = obj(path)
    assert e['kineticloop_evidence'] == 'gzip-v1'
    assert Path(e['payload']).parent == Path(path).parent
    stored = blob(R, e['payload'])
    assert len(stored) == e['stored_bytes'] and hashlib.sha256(stored).hexdigest() == e['stored_sha256']
    raw = gzip.decompress(stored)
    assert len(raw) == e['raw_bytes'] and hashlib.sha256(raw).hexdigest() == e['raw_sha256']
    raw_identities[path] = dict(bytes=len(raw), sha256=e['raw_sha256'], tested=e['tested_commit'],
                               command=e['command'], exit_code=e['exit_code'])
    return e, raw

record_path = 'docs/exec-plans/governance/HG-060.yaml'
record = yaml.safe_load(blob(R, record_path))
Draft202012Validator(obj('HARNESS_CHANGE.schema.json')).validate(record)
assert (record['base_commit'], record['tested_commit'], record['change_status']) == (B, T, 'PASS')
changed = git('diff', '--name-only', B, R).decode().splitlines()
assert set(record['files_changed']) == set(changed)
checks = obj(OWN + 'checks-5c1b24369df3/CHECK_INDEX.json')['checks']
assert {c['check_id'] for c in checks} == {'definitions','validator','unit','harness','lint','typecheck','authority','diff'}
assert len(checks) == 8
summaries = []
for c, declared in zip(checks, record['checks_run'], strict=True):
    assert c['tested_commit'] == T and c['exit_code'] == 0 and c['command'] == shlex.join(c['argv'])
    assert (c['check_id'], c['command'], c['output_ref']) == (declared['check_id'], declared['command'], declared['evidence_ref'])
    assert declared['result'] == 'PASS'
    e, raw = decode(c['output_ref'])
    assert e['tested_commit'] == T and e['command'] == c['command'] and e['exit_code'] == 0
    if c['check_id'] not in ('validator','unit','harness'):
        if c['check_id'] == 'definitions': assert json.loads(raw)['status'] == 'PASS'
        if c['check_id'] == 'authority': assert b'HARNESS_CHECK_PASS' in raw and b'HARNESS_CHECK_FAIL' not in raw
        if c['check_id'] == 'diff': assert raw == b''
        summaries.append(dict(check=c['check_id'], exit_code=0, raw_sha256=e['raw_sha256']))
        continue
    decoded = {}
    for p in c['evidence_refs']:
        e2, value = decode(p)
        assert e2['tested_commit'] == T and e2['exit_code'] == 0
        execution_command = shlex.join(c['harness_manifest']['command']) if c['check_id'] == 'harness' else c['command']
        collection_command = shlex.join(c['harness_manifest']['collection_command'] if c['check_id'] == 'harness' else c['collection_argv'])
        expected_command = collection_command if '-collection.' in p else (c['command'] if p.endswith('harness-manifest.json.json') else execution_command)
        assert e2['command'] == expected_command
        decoded[p] = value
    execution = json.loads(next(v for p,v in decoded.items() if p.endswith('-execution.json.json')))
    collection = json.loads(next(v for p,v in decoded.items() if '-collection.json.json' in p))
    junit = ET.fromstring(next(v for p,v in decoded.items() if p.endswith('-junit.xml.json')))
    nodeids = next(iter(collection['collections'].values()))
    assert len(nodeids) == c['cases'] and len(set(nodeids)) == len(nodeids)
    assert collection['errors'] == [] and collection['exit_code'] == 0
    assert execution['errors'] == [] and execution['exit_code'] == 0
    assert all(nodes == nodeids for nodes in execution['collections'].values())
    assert collections.Counter(execution['started']) == collections.Counter(nodeids)
    phase_counts = collections.Counter((p['nodeid'], p['phase'], p['outcome']) for p in execution['reports'])
    assert len(phase_counts) == 3*len(nodeids)
    assert all(phase_counts[(n, phase, 'passed')] == 1 for n in nodeids for phase in ('setup','call','teardown'))
    expected = []
    for n in nodeids:
        address, bracket, parameters = n.partition('[')
        file, *rest = address.split('::')
        expected.append(('.'.join([file.removesuffix('.py').replace('/', '.'), *rest[:-1]]), rest[-1]+bracket+parameters))
    cases = junit.findall('.//testcase')
    assert collections.Counter((x.attrib['classname'],x.attrib['name']) for x in cases) == collections.Counter(expected)
    assert not junit.findall('.//failure') and not junit.findall('.//error') and not junit.findall('.//skipped')
    assert len(cases) == c['cases']
    for suite in junit.findall('testsuite'):
        assert all(int(suite.attrib[k]) == 0 for k in ('errors','failures','skipped'))
    assert re.search(rb'\b'+str(c['cases']).encode()+rb' passed\b', raw)
    if c['check_id'] == 'harness':
        assert len(execution['collections']) == 2
        manifest = json.loads(next(v for p,v in decoded.items() if p.endswith('harness-manifest.json.json')))
        assert manifest == c['harness_manifest'] and manifest['execution_complete'] and manifest['errors'] == []
        assert manifest['tested_commit'] == T and manifest['dirty_source'] is False
        names = {'collection.json':'-collection.json.json', 'collection.log':'-collection.log.json', 'execution.json':'-execution.json.json', 'junit.xml':'-junit.xml.json', 'pytest.log':'-pytest.log.json'}
        for f in manifest['files']:
            value = next(v for p,v in decoded.items() if p.endswith(names[f['path']]))
            assert len(value) == f['bytes'] and hashlib.sha256(value).hexdigest() == f['sha256']
    summaries.append(dict(check=c['check_id'], cases=len(cases), collection_execution_junit_identity='PASS',
                          worker_collections=list(execution['collections']), successful_phases=len(phase_counts)))

suffix = git('rev-list','--reverse',T+'..'+R).decode().splitlines()
assert git('merge-base',T,R).decode().strip() == T
suffix_paths = {}
for commit in suffix:
    parents = git('rev-list','--parents','-n','1',commit).decode().split()
    assert len(parents) == 2
    paths = git('diff','--name-only',parents[1],commit).decode().splitlines()
    assert all(p == record_path or p.startswith(OWN) for p in paths)
    assert all(not git('ls-tree',T,'--',p).strip() for p in paths), 'post-T replacement'
    suffix_paths[commit] = paths

# Independently recheck original declarations and source membership/ancestry.
declarations = obj('docs/harness/REVIEW_SOURCE_DECLARATIONS.json')
assert declarations['declarations'][:6] == obj('docs/harness/REVIEW_SOURCE_DECLARATIONS.json',B)['declarations']
assert len(declarations['declarations']) == 8
source_rows = []
for d in declarations['declarations'][6:]:
    original = blob(d['original_review_record_commit'],d['review_record_path'])
    assert hashlib.sha1(b'blob '+str(len(original)).encode()+b'\0'+original).hexdigest() == d['original_review_record_blob']
    review = json.loads(original)
    Draft202012Validator(obj('THREAD_REVIEW.schema.json')).validate(review)
    assert review['task_identity'] == d['owner'] and review['review_type'] == d['review_type'] == 'GENERAL'
    assert review['reviewed_head_sha'] == d['reviewed_head_sha'] and d['reference'] in review['evidence_refs']
    assert d['purpose'] == 'REVIEW_SOURCE_INSPECTION'
    git('merge-base','--is-ancestor',d['original_review_record_commit'],B)
    git('merge-base','--is-ancestor',d['reviewed_head_sha'],d['original_review_record_commit'])
    assert original == blob(B,d['review_record_path']) == blob(R,d['review_record_path'])
    source = blob(d['reviewed_head_sha'],d['reference'])
    assert len(source) == 14776 and hashlib.sha256(source).hexdigest() == '0cac4692d4188b5bfb9cfa3f9d6436ba905ebe8d8c90640f2445eea69f28b8b7'
    source_rows.append(dict(owner=d['owner'], source_sha256=hashlib.sha256(source).hexdigest(), purpose='source inspection; test implementation and separate output refs'))


# Native classification of exact nine historical reports; no historical source import.
preservation = obj(OWN+'PRESERVATION_DISPOSITION.json')
preservation_rows = []
for row in preservation['entries']:
    pin = row['original']
    data = blob(pin['revision'],pin['path'])
    assert compact.envelope(data) is None and compact.reencoding_record(data) is None
    assert not compact.embedded_raw(json.loads(data))
    assert len(data) == pin['bytes'] and hashlib.sha256(data).hexdigest() == pin['sha256']
    preservation_rows.append(dict(path=pin['path'], bytes=len(data), sha256=pin['sha256'], native_classification='ordinary'))
assert len(preservation_rows) == 9
superseded = []
for short in ('290d5fc262f3','e821c542b788'):
    state = obj(OWN+'superseded-'+short+'/ROUND_STATE.json')
    assert state['harness'] == dict(state='INTERRUPTED',actual_cli_exit=-15,driver_exit=241,pytest_exit=None,execution_complete=False)
    assert all(v == 'NOT_RUN' for v in state['remaining'].values())
    assert set(state['completed']) == {'definitions','validator','unit'}
    assert all(c['tested_commit'] == state['tested_commit'] and c['exit_code'] == 0 for c in state['completed'].values())
    for artifact in state['artifacts']:
        e,value = decode(artifact['evidence_ref'])
        assert e['tested_commit'] == state['tested_commit'] and e['command'] == artifact['command']
        assert e['exit_code'] == artifact['observed_exit'] and len(value) == artifact['bytes']
        assert hashlib.sha256(value).hexdigest() == artifact['sha256']
    partial = state['partial_child_output']
    value = blob(R,partial['path'])
    assert partial['command_exit_code'] is None and len(value) == partial['bytes']
    assert hashlib.sha256(value).hexdigest() == partial['sha256']
    superseded.append(dict(tested=state['tested_commit'], interrupted=True, actual_cli_exit=-15,driver_exit=241, child_exit=None, preserved_artifacts=len(state['artifacts'])))

report = dict(status='PASS',reviewed=R,base=B,tested=T,changed_files=len(changed), checks=summaries,
              source_additions=source_rows, preservation=preservation_rows, superseded=superseded, tested_result_suffix=suffix_paths, raw_identities=raw_identities)
(OUT/'audit.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(status='PASS',reviewed=R,checks=summaries,decoded_objects=len(raw_identities))))
