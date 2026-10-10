"""Capture real HG062 check bytes and build its result only after identity verification."""
import hashlib
import json
import platform
import shlex
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]
BASE = '4e9c60a242d84b81b6e82b635da6c7227af68912'
T = sys.argv[1]
assert len(T) == 40 and all(c in '0123456789abcdef' for c in T)
SCRATCH = Path('/private/tmp/hg062-author-' + T[:12])
DEST = 'docs/exec-plans/evidence/HG-062/checks-' + T[:12] + '/'
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == T
assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT)
FROZEN_MANIFEST = (ROOT / 'HARNESS_DOCUMENT_MANIFEST.json').read_bytes()
assert FROZEN_MANIFEST == subprocess.check_output(['git', 'show', T + ':HARNESS_DOCUMENT_MANIFEST.json'], cwd=ROOT)
assert 'docs/exec-plans/governance/HG-062.yaml' not in {entry['path'] for entry in json.loads(FROZEN_MANIFEST)['files']}
sys.path.insert(0, str(ROOT))
from tools.harness.compact_evidence import capture


def identity(path):
    raw = path.read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def verify_identities(collection_path, execution_path, junit_path, workers):
    collection = json.loads(collection_path.read_text())
    execution = json.loads(execution_path.read_text())
    assert collection['exit_code'] == execution['exit_code'] == 0
    assert not collection['errors'] and not execution['errors']
    nodes = collection['collections']['serial']
    assert len(nodes) == len(set(nodes)) > 0
    assert len(execution['collections']) == workers
    assert all(items == nodes for items in execution['collections'].values())
    assert Counter(execution['started']) == Counter(nodes)
    assert len(execution['started']) == len(set(execution['started']))
    for phase in ('setup', 'call', 'teardown'):
        rows = [row for row in execution['reports'] if row['phase'] == phase]
        assert Counter(row['nodeid'] for row in rows) == Counter(nodes)
        assert all(row['outcome'] == 'passed' for row in rows)
    junit = ET.parse(junit_path).getroot()
    cases = junit.findall('.//testcase')
    assert len(cases) == len(nodes)
    assert not junit.findall('.//failure') and not junit.findall('.//error') and not junit.findall('.//skipped')
    expected = []
    for node in nodes:
        address, separator, params = node.partition('[')
        parts = address.split('::')
        expected.append(('.'.join([parts[0][:-3].replace('/', '.'), *parts[1:-1]]), parts[-1] + separator + params))
    assert Counter(expected) == Counter((case.get('classname'), case.get('name')) for case in cases)
    return len(nodes)


names = ('definitions', 'validator', 'unit', 'harness', 'lint', 'typecheck', 'authority', 'diff')
index = {'base_commit': BASE, 'tested_commit': T, 'checks': [], 'runtime': {
    'executable': sys.executable, 'version': sys.version, 'platform': platform.platform(),
    'fallback_reason': 'uv unavailable; approved existing Python3.12 environment and dependency paths'},
    'dependency_provenance': json.loads((ROOT / 'docs/exec-plans/evidence/HG-062/DEPENDENCY_PROVENANCE.json').read_text()),
    'meaning': 'Eight HG062 author checks only; historical execution, production recognizer and root gates are unclaimed'}
for package in index['dependency_provenance']['packages']:
    for item in package['source_files'] + package['metadata_files']:
        assert identity(Path(item['path'])) == {key: item[key] for key in ('bytes', 'sha256')}
records = []
# Validate everything before writing any evidence so failures cannot yield partial PASS records.
for name in names:
    meta = json.loads((SCRATCH / (name + '-command.json')).read_text())
    assert meta['base_commit'] == BASE and meta['tested_commit'] == T
    assert meta['exit_code'] == 0 and meta['execution_state'] == 'COMPLETED'
    assert meta['command'] == shlex.join(meta['argv'])
    sources = [(SCRATCH / (name + '.log'), name + '.json', meta['command'], meta['environment'])]
    if name in ('validator', 'unit'):
        assert meta['collection_exit'] == 0
        meta['cases'] = verify_identities(SCRATCH / (name + '-collection.json'),
            SCRATCH / (name + '-execution.json'), SCRATCH / (name + '-junit.xml'), 1)
        for suffix in ('collection.log', 'collection.json', 'execution.json', 'junit.xml'):
            collecting = suffix.startswith('collection')
            sources.append((SCRATCH / (name + '-' + suffix), name + '-' + suffix + '.json',
                meta['collection_command'] if collecting else meta['command'],
                meta['collection_environment'] if collecting else meta['environment']))
    if name == 'harness':
        directory = SCRATCH / 'harness-run'
        manifest = json.loads((directory / 'manifest.json').read_text())
        assert manifest['exit_code'] == manifest['pytest_exit_code'] == 0 and not manifest['errors']
        assert manifest['tested_commit'] == T and not manifest['dirty_source']
        assert manifest['execution_complete'] and manifest['mode'] == 'EXECUTION'
        assert manifest['workers'] == 2
        meta['cases'] = verify_identities(directory / 'collection.json', directory / 'execution.json', directory / 'junit.xml', 2)
        inner_env = dict(meta['environment'],
            PYTHONPATH=str(ROOT) + ':' + str(ROOT / 'src') + ':' + meta['environment']['PYTHONPATH'],
            KINETICLOOP_HARNESS_ROOT=str(ROOT), KINETICLOOP_HARNESS_WORKERS='2',
            KINETICLOOP_HARNESS_OBSERVER=str(directory / 'execution.json'))
        collect_env = dict(inner_env, KINETICLOOP_HARNESS_OBSERVER=str(directory / 'collection.json'))
        meta['inner_environment_provenance'] = 'Exact environment additions from tested tools/harness/run_harness_tests.py and recorded outer environment'
        meta['execution_environment'] = inner_env
        meta['collection_environment'] = collect_env
        for file in sorted(directory.iterdir()):
            if file.is_file():
                command = shlex.join(manifest['collection_command']) if file.name.startswith('collection') else (
                    shlex.join(manifest['command']) if file.name in ('execution.json', 'junit.xml', 'pytest.log') else meta['command'])
                sources.append((file, 'harness-' + file.name + '.json', command, collect_env if file.name.startswith('collection') else inner_env if file.name in ('execution.json', 'junit.xml', 'pytest.log') else meta['environment']))
        meta['harness_manifest'] = manifest
    meta['capture_sources'] = sources
    index['checks'].append(meta)

(ROOT / DEST).mkdir(exist_ok=False)
for meta in index['checks']:
    artifacts = []
    for source, basename, command, environment in meta.pop('capture_sources'):
        ref = DEST + basename
        raw = source.read_bytes()
        # Same bytes can share storage, but every fresh observation gets a new T-bound envelope.
        prior_payloads = sorted((ROOT / 'docs/exec-plans/evidence/HG-062').rglob(hashlib.sha256(raw).hexdigest() + '.gz'))
        if prior_payloads and prior_payloads[0].parent != ROOT / DEST:
            ref = str(prior_payloads[0].parent.relative_to(ROOT)) + '/fresh-' + T[:12] + '-' + basename
        assert not (ROOT / ref).exists()
        envelope = capture(ROOT, ref, raw, T, command, 0,
                           datetime.fromtimestamp(meta['started_at_unix'], timezone.utc).isoformat())
        artifacts.append({'source_file': str(source), 'evidence_ref': ref, 'command': command,
                          'environment': environment, 'raw_identity': identity(source),
                          'envelope_identity': identity(ROOT / ref), 'payload_identity': identity(ROOT / envelope['payload'])})
    meta['artifacts'] = artifacts
    meta['output_ref'] = artifacts[0]['evidence_ref']
    records.append({'check_id': meta['check_id'], 'command': meta['command'], 'result': 'PASS', 'evidence_ref': meta['output_ref']})
(ROOT / DEST / 'CHECK_INDEX.json').write_text(json.dumps(index, indent=2) + '\n')
Path('/private/tmp/hg062-checks.json').write_text(json.dumps(records, indent=2) + '\n')
# Snapshot result path before deriving the exact complete base-to-result changed paths.
result_path = ROOT / 'docs/exec-plans/governance/HG-062.yaml'
result_path.write_text('')
tracked = subprocess.check_output(['git', 'diff', '--name-only', BASE], cwd=ROOT, text=True).splitlines()
untracked = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard'], cwd=ROOT, text=True).splitlines()
files = sorted(set(tracked + untracked))
record = {
    'change_identity': 'harness-governance-v0.1/HG-062', 'display_change_id': 'HG-062',
    'base_commit': BASE, 'tested_commit': T, 'change_status': 'PASS',
    'summary': 'HG062 definitions-only unverified historical documentary forms and HG058 prospective refinement. All eight fresh author checks pass at exact T with positive identity equality; original historical semantics, producer execution and review acceptance remain unverified. Root reviews and gates are separate.',
    'packets_refined': [], 'files_changed': files, 'checks_run': records, 'frozen_impact': 'NONE',
    'authority_entries_added': [],
    'known_limitations': [
        'Five closed documentary forms only; original claim bindings are not verified semantics, historical producer execution or review acceptance. HG047 strict RRO failure remains failure. No historical source is executed/imported/evaluated.',
        'The task-owned fixture oracle is definitions-only; future production recognition and inventory counts belong to SAME HG058 after actual normal HG062 merge and coordinator regrant.',
        'All eight checks ran freshly at exact tested_commit. CHECK_INDEX records actual argv/environment/exits and complete positive collection/execution/JUnit identity equality. No research advisory or historical execution is reused.',
        'Manifest, index and helpers are frozen at T. Own mutable result is not registered in the manifest. T-to-R adds only this result and new own evidence; unchanged suffix validation remains required.',
        'GENERAL and SECURITY_DATA_BOUNDARY independent actual-R reviews are pending, as are final audits, installed-bundle review/install, exact admission, App/unit/harness/fullDB/cleanup, hosted gates and normal protected merge.',
        'HG058 remains frozen3965; original auditbase9700/live-base distinction, source/map/failure history, eight tuples/four callers/nine metadata and all independent selected/storage/source/decoder/RRO/M3/admission guards remain unchanged.',
        'The first candidate a4f823f9291106389e2ac538c308c34cd19f276c was invalidated by self-review for missing explicit selected-display-alias fixture coverage. Its definitions exit0, validator collection exit0 and intentionally interrupted validator exit2 after75 passes remain in invalidated-a4f823f92911/PRESERVATION.json and ancestry. No prior execution is reused.',
        'Candidate f54b7e3b3d2242c2ac97d5329f7f9a5d2a55be82 was invalidated by self-review for a zero-count false-verification-label fixture gap. Its definitions/validator170/unit247 exits0 and intentionally interrupted harness exit2 after1103 passes, including incomplete identity diagnostics, remain in invalidated-f54b7e3b3d22/PRESERVATION.json and ancestry. No prior execution is reused.',
        'Original R cf203ab10c1e5979fb2f414211d42c48d7f95795 and all eight author checks remain in ancestry/evidence. Actual R1 GENERAL PASS and SECURITY_DATA_BOUNDARY CHANGES_REQUIRED are preserved under own reviews. The correction rejects bound original parent contradictions and requires role-specific component reference/command linkage, including the comparison benchmark conjunction. Prior GENERAL PASS is stale for this new R; both fresh reviews are required. No old check execution supplies current acceptance.',
        'No product or requirement status is promoted. packets_refined stays empty under existing KL-only schema; summary/files identify HG058 refinement.',
    ]}
result_path.write_text(yaml.safe_dump(record, sort_keys=False, width=110))
assert (ROOT / 'HARNESS_DOCUMENT_MANIFEST.json').read_bytes() == FROZEN_MANIFEST
state_path = Path('/private/tmp/hg062-worker-state.json'); state = json.loads(state_path.read_text())
state.pop('failed_check', None)
state.update(current_failures=[], phase='eight author checks PASS; lossless compact evidence and result ready to commit',
             check_index=DEST + 'CHECK_INDEX.json', result_path=str(result_path),
             cases={meta['check_id']:meta.get('cases') for meta in index['checks']})
state_path.write_text(json.dumps(state, indent=2) + '\n')
print(json.dumps({'checks': len(records), 'cases': state['cases'], 'artifacts': len(list((ROOT / DEST).iterdir())),
                  'capture_bytes': sum(file.stat().st_size for file in (ROOT / DEST).iterdir()), 'files_changed': len(files)}))
