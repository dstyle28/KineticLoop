"""Read-only SHA-bound audit; never emit recovered data or credential material."""
import hashlib
import json
import pathlib
import re
import subprocess
import xml.etree.ElementTree as ET
import zlib
from collections import Counter
ROOT = pathlib.Path(__file__).resolve().parents[5]
HEAD = '96ebb9e0e95211fc684273e7b69a49dc11e11e87'
BASE = 'af09be228fbc89d074b6e863c83e1fdda343d55b'
TESTED = '6a3f10ef424f41bb690d8835f952484b0ca4f87b'
INDEX = 'docs/exec-plans/evidence/KL-036/checks-' + TESTED + '-11edd5b3/CHECK_INDEX.json'

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)

def blob(path):
    assert str(pathlib.PurePosixPath(path)) == path and '..' not in pathlib.PurePosixPath(path).parts
    row = git('ls-tree', HEAD, '--', path).decode().strip()
    assert row.startswith('100644 blob ') or row.startswith('100755 blob '), path
    return git('show', HEAD + ':' + path)

def raw(path):
    data = blob(path)
    try:
        envelope = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        return (data, None)
    if not isinstance(envelope, dict) or envelope.get('kineticloop_evidence') != 'gzip-v1':
        return (data, None)
    payload = envelope['payload']
    assert pathlib.PurePosixPath(payload).parent == pathlib.PurePosixPath(path).parent
    stored = blob(payload)
    assert len(stored) == envelope['stored_bytes']
    assert hashlib.sha256(stored).hexdigest() == envelope['stored_sha256']
    decoder = zlib.decompressobj(31)
    recovered = decoder.decompress(stored, 64 * 1024 * 1024 + 1)
    assert decoder.eof and (not decoder.unused_data) and (not decoder.unconsumed_tail)
    assert len(recovered) == envelope['raw_bytes'] <= 64 * 1024 * 1024
    assert hashlib.sha256(recovered).hexdigest() == envelope['raw_sha256']
    assert pathlib.PurePosixPath(payload).name == envelope['raw_sha256'] + '.gz'
    return (recovered, envelope)

def junit_identity(node):
    address, separator, parameters = node.partition('[')
    parts = address.split('::')
    return ('.'.join([parts[0][:-3].replace('/', '.'), *parts[1:-1]]), parts[-1] + separator + parameters)

def main():
    assert subprocess.run(['git', 'merge-base', '--is-ancestor', TESTED, HEAD], cwd=ROOT).returncode == 0
    suffix = git('diff', '--name-only', TESTED, HEAD).decode().splitlines()
    assert all((p.startswith('docs/exec-plans/evidence/KL-036/') or p == 'docs/exec-plans/completed/KL-036_RESULT.yaml' for p in suffix))
    index = json.loads(blob(INDEX))
    assert index['tested_commit'] == TESTED and len(index['runs']) == 16
    checks = []
    witness_summary = {}
    for run in index['runs']:
        assert run['tested_commit'] == TESTED and run['exit_code'] == 0 and (run['status'] == 'PASS') and (not run['errors'])
        artifacts = {}
        for kind, path in run['artifacts'].items():
            data, envelope = raw(path)
            assert envelope and envelope['tested_commit'] == TESTED and (envelope['exit_code'] == 0)
            command = run.get('collection_command', run['command']) if kind.startswith('collection.') else run['command']
            assert envelope['command'] == command
            artifacts[kind] = data
        prefix = 'runner/' if 'runner/execution.json' in artifacts else ''
        if prefix + 'execution.json' in artifacts:
            collection = json.loads(artifacts[prefix + 'collection.json'])
            execution = json.loads(artifacts[prefix + 'execution.json'])
            assert not collection['errors'] and collection['exit_code'] == 0
            assert not execution['errors'] and execution['exit_code'] == 0
            nodes = next(iter(collection['collections'].values()))
            assert nodes and len(nodes) == len(set(nodes))
            assert all((Counter(v) == Counter(nodes) for v in execution['collections'].values()))
            assert Counter(nodes) == Counter(execution['started'])
            for phase in ('setup', 'call', 'teardown'):
                reports = [r for r in execution['reports'] if r['phase'] == phase]
                assert Counter((r['nodeid'] for r in reports)) == Counter(nodes)
                assert all((r['outcome'] == 'passed' for r in reports))
            cases = ET.fromstring(artifacts[prefix + 'junit.xml']).findall('.//testcase')
            assert Counter(map(junit_identity, nodes)) == Counter(((c.get('classname'), c.get('name')) for c in cases))
            assert all((c.find('failure') is None and c.find('error') is None and (c.find('skipped') is None) for c in cases))
            assert len(nodes) == run['collected'] == run['executed'] == run['junit']
            if prefix:
                manifest = json.loads(artifacts['runner/manifest.json'])
                assert manifest['tested_commit'] == TESTED and (not manifest['dirty_source']) and manifest['execution_complete'] and (not manifest['errors'])
            stdout = artifacts[prefix + 'collection.log'].decode()
            for node in nodes:
                assert node in stdout
        log = artifacts['execution.log'].decode()
        witnesses = [json.loads(line.split('WORKER_REAPER_EVIDENCE ', 1)[1]) for line in log.splitlines() if 'WORKER_REAPER_EVIDENCE ' in line]
        if witnesses:
            by_kind = Counter((w['kind'] for w in witnesses))
            before = next((w for w in witnesses if w['kind'] == 'before_inventory'))
            after = next((w for w in witnesses if w['kind'] == 'after_inventory'))
            assert before['inventory'] == after['inventory']
            assert after['foreign_unchanged'] and after['owned_resources_removed']
            assert before['tested_commit'] == TESTED
            namespace = before['namespace']
            digest = hashlib.sha256(bytes(pathlib.Path(before['resolved_root']).resolve())).hexdigest()[:12]
            assert namespace == {'database_name': f'kineticloop_kl036_{TESTED[:7]}_{digest}', 'project_name': f'kineticloop-kl036-{TESTED[:7]}-{digest}'}
            witness_summary[run['check_id']] = dict(by_kind)
        checks.append({'check_id': run['check_id'], 'exit_code': 0, 'collected': run.get('collected'), 'executed': run.get('executed'), 'junit': run.get('junit'), 'verified_artifacts': len(artifacts)})
    changed = git('diff', '--name-only', BASE, HEAD, '--', 'docs/exec-plans/evidence/KL-036').decode().splitlines()
    suspicious = []
    envelopes = 0
    for path in changed:
        if path.endswith(('.gz', '.py')):
            continue
        data, envelope = raw(path)
        envelopes += bool(envelope)
        inspected = data.replace(b'test_compose_non_readiness_and_wrong_endpoint_rejected[kineticloop-local-only-changed]', b'')
        if re.search(b'postgres(?:ql)?://', inspected) or b'kineticloop-local-only' in inspected or b'kl072-local-only' in inspected:
            suspicious.append(path)
    assert not suspicious, suspicious
    record = json.loads(blob('docs/exec-plans/evidence/KL-036/failed-ebe7ade-sanitized/FAILURE_RECORD.json'))
    quarantine = []
    for entry in record['records']:
        local = pathlib.Path(entry['original_path'])
        data = local.read_bytes()
        assert len(data) == entry['original_bytes'] and hashlib.sha256(data).hexdigest() == entry['original_sha256']
        assert local.parent.parent.stat().st_mode & 511 == 448
        quarantine.append({'sha256': entry['original_sha256'], 'bytes': len(data), 'hash_verified': True})
    output = {'reviewed_head_sha': HEAD, 'base_commit': BASE, 'tested_commit': TESTED, 'tested_suffix_only_result_and_own_evidence': True, 'checks': checks, 'witness_kind_counts': witness_summary, 'changed_evidence_envelopes_verified': envelopes, 'credential_guard_matches_outside_exact_synthetic_identifier': 0, 'quarantined_originals_hash_verified_without_output': quarantine}
    (pathlib.Path(__file__).parent / 'AUDIT.json').write_text(json.dumps(output, indent=2) + '\n')
    print(json.dumps({'verified_checks': len(checks), 'verified_envelopes': envelopes, 'credential_matches': 0, 'quarantine_hashes_verified': len(quarantine)}))
if __name__ == '__main__':
    main()
