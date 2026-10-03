from pathlib import Path
import gzip
import hashlib
import importlib.util
import json
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parent
BASE = 'b877db0edd2e4550d6ea81750656112fb7f2e223'
TESTED = '5debfe1b41a26c0b3f985917b80995a9eb38b92e'
REVIEWED = '7141b1dfe48df8f0e25429cf9ff646af6de4b5ce'

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

ce = load_module('hg051_db_ce', 'tools/harness/compact_evidence.py')
v = load_module('hg051_db_validator', 'tools/harness/validate_harness.py')
lines = ['HG051 independent DB/concurrency review probes', 'Protected base: ' + BASE,
         'Task tested revision: ' + TESTED, 'Reviewed implementation: ' + REVIEWED]
assert git('rev-parse', 'HEAD').decode().strip() == REVIEWED
assert subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, REVIEWED], cwd=ROOT).returncode == 0
assert subprocess.run(['git', 'merge-base', '--is-ancestor', TESTED, REVIEWED], cwd=ROOT).returncode == 0
changed = git('diff', '--no-renames', '--name-only', BASE, REVIEWED).decode().splitlines()
assert all(v.matches(path, v.governance_allowed_patterns('HG-051')) for path in changed)
assert not any(path.startswith(('src/', 'migrations/', 'tests/db/', '.github/')) for path in changed)
frozen = json.loads(git('show', BASE + ':FROZEN_BASELINE.json'))
protected = {'FROZEN_BASELINE.json'} | {item['path'] for item in frozen['files']}
for path in protected:
    assert git('rev-parse', BASE + ':' + path) == git('rev-parse', REVIEWED + ':' + path)
lines.append('PASS: exact scope and frozen identities; no runtime, DB test, migration, workflow or coordination owner change.')
historical = git('ls-tree', '-r', '--name-only', BASE, '--', 'docs/exec-plans/completed',
                 'docs/exec-plans/reviews', 'docs/exec-plans/evidence').decode().splitlines()
def tree(revision):
    entries = git('ls-tree', '-r', '-z', revision).split(b'\0')
    return {entry.split(b'\t', 1)[1].decode(): entry.split(b'\t', 1)[0]
            for entry in entries if entry}
old_tree, reviewed_tree = tree(BASE), tree(REVIEWED)
for path in historical:
    assert old_tree[path] == reviewed_tree[path]
lines.append('PASS: all ' + str(len(historical)) + ' existing base historical artifacts retain their Git object identities.')
delta = git('diff', '--name-only', TESTED, REVIEWED).decode().splitlines()
assert all(path == 'docs/exec-plans/governance/HG-051.yaml' or
           path.startswith('docs/exec-plans/evidence/HG-051/final-5debfe1/') for path in delta)
lines.append('PASS: tested-to-reviewed delta adds check capture and governance record only; tested implementation unchanged.')
index = json.loads(git('show', REVIEWED + ':CURRENT_DOCUMENT_INDEX.json'))
for item in index['documents'] + index['machine_readable']:
    assert hashlib.sha256(git('show', REVIEWED + ':' + item['path'])).hexdigest() == item['sha256']
lines.append('PASS: all indexed current authority hashes match exact reviewed blobs.')
for original in ce.historical_originals():
    raw = ce.archive_original(ROOT, original)
    assert git('rev-parse', original['revision'] + ':' + original['path']).decode().strip() == original['blob_id']
    record, stored = ce.archive_envelope(original, raw)
    assert gzip.decompress(stored) == raw
    assert ce.read(ROOT, original['path'], original['revision']) == raw
    assert subprocess.run(['git', 'merge-base', '--is-ancestor', original['revision'],
                           '477b213f67429f571b60d5701f02892ab9c1cbbf'], cwd=ROOT).returncode == 0
    ce.verify_historical_ref(ROOT, original['execution_record'], '477b213f67429f571b60d5701f02892ab9c1cbbf')
    lines.append('PASS: original ' + original['path'] + ': ' + str(len(raw)) +
                 ' bytes; exact regular blob/hash; lossless gzip; recorded outcome ' +
                 original['execution']['result'] + ' exit ' + str(original['execution']['exit_code']) +
                 '; unknown timestamp retained.')
assert not git('ls-tree', REVIEWED, '--', ce.MAPPING_PATH).strip()
assert ce.archive_audit(ROOT, REVIEWED)[0] == []
assert (ce.PLAIN_LIMIT, ce.STORED_LIMIT, ce.RAW_LIMIT, ce.TOTAL_LIMIT) == (262144, 8388608, 67108864, 16777216)
lines.append('PASS: actual KL080 archival migration absent; four original objects available; numeric budgets unchanged.')
import yaml
governance = yaml.safe_load(git('show', REVIEWED + ':docs/exec-plans/governance/HG-051.yaml'))
assert governance['tested_commit'] == TESTED
for check in governance['checks_run']:
    manifest = json.loads(ce.blob(ROOT, check['evidence_ref'], REVIEWED))
    raw = ce.read(ROOT, check['evidence_ref'], REVIEWED, tested=TESTED,
                  command=check['command'], exit_code=0)
    assert check['result'] == 'PASS'
    lines.append('PASS: bound committed check ' + check['check_id'] + ' decodes exact execution bytes; exit zero.')
for name, count in [('focused', 184), ('harness', 1486), ('unit', 241)]:
    raw = ce.read(ROOT, f'docs/exec-plans/evidence/HG-051/final-5debfe1/{name}.json', REVIEWED)
    assert str(count).encode() + b' passed' in raw
for name, count in [('focused-junit', 184), ('harness-junit-xml', 1486), ('unit-junit', 241)]:
    doc = ET.fromstring(ce.read(ROOT, f'docs/exec-plans/evidence/HG-051/final-5debfe1/{name}.json', REVIEWED))
    cases = list(doc.iter('testcase'))
    assert len(cases) == count
    assert all(not list(case.iter('failure')) and not list(case.iter('error')) and
               not list(case.iter('skipped')) for case in cases)
    lines.append('PASS: committed ' + name + ' contains ' + str(count) + ' successful cases with zero failures/errors/skips.')
collection = json.loads(ce.read(ROOT, 'docs/exec-plans/evidence/HG-051/final-5debfe1/harness-collection-json.json', REVIEWED))
execution = json.loads(ce.read(ROOT, 'docs/exec-plans/evidence/HG-051/final-5debfe1/harness-execution-json.json', REVIEWED))
nodeids = collection['collections']['serial']
assert len(nodeids) == len(set(nodeids)) == 1486
assert len(execution['started']) == 1486
assert set(nodeids) == set(execution['started'])
assert all(case['outcome'] == 'passed' for case in execution['reports'])
assert execution['exit_code'] == 0 and not execution['errors']
lines.append('PASS: full harness collection and actual execution agree on 1486 unique node IDs; every setup/call/teardown outcome passed.')
assert git('rev-parse', 'HEAD').decode().strip() == REVIEWED
lines.append('Limits: these are storage/governance probes; full PostgreSQL concurrency/App/hosted gates are NOT_RUN and earn no product/M3/KL080/release closure credit.')
(OUT / 'probe.log').write_text('\n'.join(lines) + '\n')
print('Independent DB/governance provenance and execution probes PASS; see probe.log')
