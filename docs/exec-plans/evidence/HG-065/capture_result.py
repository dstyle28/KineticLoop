"""Capture real HG065 check bytes and build its result only after identity verification."""
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
BASE = 'e8e93bd32a83bd2fd6bf89951863d59b37e9d2b3'
T = sys.argv[1]
assert len(T) == 40 and all(c in '0123456789abcdef' for c in T)
SCRATCH = Path('/private/tmp/hg065-author-' + T[:12])
DEST = 'docs/exec-plans/evidence/HG-065/checks-' + T[:12] + '/'
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == T
assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT)
FROZEN_MANIFEST = (ROOT / 'HARNESS_DOCUMENT_MANIFEST.json').read_bytes()
assert FROZEN_MANIFEST == subprocess.check_output(['git', 'show', T + ':HARNESS_DOCUMENT_MANIFEST.json'], cwd=ROOT)
assert 'docs/exec-plans/governance/HG-065.yaml' not in {entry['path'] for entry in json.loads(FROZEN_MANIFEST)['files']}
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
    'dependency_provenance': json.loads((ROOT / 'docs/exec-plans/evidence/HG-065/DEPENDENCY_PROVENANCE.json').read_text()),
    'meaning': 'Eight HG065 author checks only; historical execution, production recognizer and root gates are unclaimed'}
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
    if name == 'definitions':
        lines = (SCRATCH / 'definitions.log').read_text().splitlines()
        definition_report = json.loads(lines[-1])
        assert definition_report['tested_commit'] == T and definition_report['definition_checks'] == 156
        meta['cases'] = 156
        definitions_dir = Path(definition_report['observations'])
        reproduced = definitions_dir / 'ACTUAL_CUSTODY_PROOF.json'
        canonical = ROOT / 'docs/exec-plans/evidence/HG-065/ACTUAL_CUSTODY_PROOF.json'
        assert reproduced.read_bytes() == canonical.read_bytes()
        meta['fresh_reproduced_custody_proof'] = dict(identity(reproduced), evidence_ref=str(canonical.relative_to(ROOT)))
        for file in sorted(definitions_dir.iterdir()):
            if file.is_file() and file.name != 'ACTUAL_CUSTODY_PROOF.json':
                sources.append((file, 'definitions-' + file.name + '.json', meta['command'], meta['environment']))
        meta['definition_report'] = definition_report
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
        prior_payloads = sorted((ROOT / 'docs/exec-plans/evidence/HG-065').rglob(hashlib.sha256(raw).hexdigest() + '.gz'))
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
Path('/private/tmp/hg065-checks.json').write_text(json.dumps(records, indent=2) + '\n')
# Snapshot result path before deriving the exact complete base-to-result changed paths.
result_path = ROOT / 'docs/exec-plans/governance/HG-065.yaml'
result_path.write_text('')
tracked = subprocess.check_output(['git', 'diff', '--name-only', BASE], cwd=ROOT, text=True).splitlines()
untracked = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard'], cwd=ROOT, text=True).splitlines()
files = sorted(set(tracked + untracked))
record = {
    'change_identity': 'harness-governance-v0.1/HG-065', 'display_change_id': 'HG-065',
    'base_commit': BASE, 'tested_commit': T, 'change_status': 'PASS',
    'summary': 'HG065 definitions-only bounded retained representation custody and exact HG058 prospective scope/check refinement. Eight fresh author checks PASS at exact T with positive identities; historical execution, native whole audit, installed operation and root gates remain unperformed.',
    'packets_refined': [], 'files_changed': files, 'checks_run': records, 'frozen_impact': 'NONE',
    'authority_entries_added': [],
    'known_limitations': [
        'Ten byte-exact reviewed normative documents define prospective custody only. The portable156-fixture oracle is task-local; its synthetic premises never construct production host authority.',
        'Fresh immutable component observations corroborate six envelopes, two payloads, eight physical paths, original declarations/schemas/pointers/graphs and own/inherited map components. Complete native whole inventory, all-map history, private installed operation and runtime eligibility remain NOT_RUN.',
        'Historical execution UNVERIFIED, acceptance_eligible=false and execution_reuse=false. Unknown6358 child stays null distinct from driver143; c4b mapping gap, three741>512 attribution denials, HG004/HG047 gaps, initial5da0FAIL and every failed/interrupted attempt remain unchanged.',
        'All156 definition identities and validator/unit/harness collection/start/setup/call/teardown/JUnit identities are positive and exact. Scratch/draft checks and preparation reviews are provenance only, never reused task acceptance.',
        'Original Q source-schema562 entries remain complete and native; projected/execution512 caps remain unchanged. Exact original auditO9700 differs from original Q then-live baseD and future liveP.',
        'Manifest/helpers frozen at T. T-to-R adds only own result/evidence. Fresh independent GENERAL/SECURITY, final compact/ci-pr, complete installation review/install, exact admission, App/fullDB/cleanup/live hosted gates and protected normal merge remain separate pending root duties.',
        'SAME HG058 remains frozen3965 until actual HG065 normal merge, completely reviewed installed readiness and root regrant. DB/App free/unreserved; no oldPR99/102 disposition, runtime permission, product/requirement/release PASS or historical rewrite.',
        'packets_refined=[] preserves the existing KL-only schema. Summary/files explicitly enumerate HG058 packet refinement; only prospective tools/harness/local_gate.py path and individual check-index duties are added.',
    ]}
result_path.write_text(yaml.safe_dump(record, sort_keys=False, width=110))
assert (ROOT / 'HARNESS_DOCUMENT_MANIFEST.json').read_bytes() == FROZEN_MANIFEST
state_path = Path('/private/tmp/hg065-worker-state.json'); state = json.loads(state_path.read_text())
state.pop('failed_check', None)
state.update(current_failures=[], phase='eight author checks PASS; lossless compact evidence and result ready to commit',
             check_index=DEST + 'CHECK_INDEX.json', result_path=str(result_path),
             cases={meta['check_id']:meta.get('cases') for meta in index['checks']})
state_path.write_text(json.dumps(state, indent=2) + '\n')
print(json.dumps({'checks': len(records), 'cases': state['cases'], 'artifacts': len(list((ROOT / DEST).iterdir())),
                  'capture_bytes': sum(file.stat().st_size for file in (ROOT / DEST).iterdir()), 'files_changed': len(files)}))
