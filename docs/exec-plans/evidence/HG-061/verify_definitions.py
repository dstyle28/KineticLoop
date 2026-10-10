"""HG061 definition/preservation check; never executes historical source or the future recognizer."""
import argparse
import ast
import hashlib
import json
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]
BASE = 'ebee712b591d14c165007cd3d56d89cb14ea1487'
OWN = 'docs/exec-plans/evidence/HG-061/'
VALIDATOR = 'tools/harness/validate_harness.py'
CONTRACT = 'docs/harness/HARNESS_GOVERNANCE_CONTRACT.md'
PACKET = 'docs/exec-plans/active/HG-058.md'
B = '2c44f456a0daf8e6933f20fc3eadc7e1869d6fff'
T = '06dab6dbb38221e7111c18811cb20b42b8cc2397'
R = 'cf0b99359d04c136d01fd4c5eeec8a23cd0bbc54'
M = '26906bd7f4444914c228e98377f2b164fee0dd5d'
PINS = {
    'PACKET.md': 'd2bd9374de7e952d8156ddea8d4b57c7a77ae3643929538f0573a191cbfee9ea',
    'INITIAL_FORM.md': 'aadd431fc6bf24e9339a08be0fa3e0ec9209220c7b645687c456a457c62b5606',
    'AUTHORITY_MAPPING.md': '6813b960fc358b083b73cbd53f50e50623ece5597332d1b4618a5b05a6df5fb5',
}
ORIGINALS = [
    (R, 'docs/exec-plans/governance/HG-044.yaml', 'fc81158bcff86b1c16cf4ae7aa19f6a8ebde01d6', 'e34e8740322f855b7f4114cccaa2c2b1992a37a37c9133ac624f02866a6b152a'),
    (R, 'docs/exec-plans/evidence/HG-044/audit.py', '2050b4b7d1293e49cff50f0feee63baf4685588f', '93791ed2b12afcbad75539ae12591ce0c7a0e3625d460c809007314486c1ae3b'),
    (R, 'docs/exec-plans/evidence/HG-044/PREPARATION.md', 'c98e1f17f3ae174ca7ae4da7f3fa9d7ad9549b23', '2c96d07fcb008f2b8b0f65493456ac9233c01c79cd6e0d97ce6ca79a1e8e75ff'),
    (R, VALIDATOR, 'ff7db2c03faeae6a4b1d12c8acd323668921223f', '1b2a5fdd04a8e87c5f74b2a4752428061d7da27dc94e30751efc801fe2af0f0d'),
    (R, 'docs/harness/M3_CLOSURE_CONTRACT.md', '1d312fb597a86041389863a6ef88577aac3b18bd', 'eacbaee3d0c72831212f29f3a3e2455e5661c1071e0c0d89ff00c81d332f342e'),
    (M, 'docs/exec-plans/reviews/HG-044/GENERAL.json', 'ba20b107f4eedc38a2dd531c6f5e4b918e00441e', '1f1d59d82d516b9e7b39f341c653808a0b86c0e6e83cff9e592e5f5b55c0f25c'),
    (M, 'docs/exec-plans/reviews/HG-044/GENERAL-r6-raw/functions.json', '61f28f1615996e042720959d5316c379af1bed60', 'b0ac954b7d1decdd7945a679a0452799edd2d94547e0701394db26ddd3d952d3'),
    (M, 'docs/exec-plans/reviews/HG-044/GENERAL-r6-raw/audit.json', '4757a0f7568496825c8238ff41fded1aa7b6a0ca', 'a53d7dc9c53ae580eaf6ee1effe8fb97a64f9f8ca23e3c502064d4100152adac'),
]
NAMES = ['milestone_closure_errors', 'm2_milestone_closure_errors',
         'm2_execution_evidence_errors', 'integration_record_errors',
         'review_evidence_exists', 'semantic_result_errors']


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, timeout=60)


def raw(revision, path):
    entry = git('ls-tree', '-l', revision, '--', path).strip()
    meta, name = entry.split(b'\t')
    mode, kind, oid, size = meta.split()
    assert mode in (b'100644', b'100755') and kind == b'blob' and name.decode() == path
    assert int(size) <= 8 * 1024 * 1024
    data = git('cat-file', 'blob', oid.decode())
    assert len(data) == int(size)
    return mode.decode(), oid.decode(), data


def spans(data):
    assert not data.startswith(b'\xef\xbb\xbf') and b'\r' not in data and b'\0' not in data
    text = data.decode('utf-8', errors='strict')
    lines = text.splitlines(keepends=True)
    result = {}
    for node in ast.parse(text).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in result
            result[node.name] = (type(node).__name__, ''.join(lines[node.lineno - 1:node.end_lineno]).encode())
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', required=True)
    parser.add_argument('--tested', required=True)
    args = parser.parse_args()
    assert args.base == BASE
    tested = git('rev-parse', args.tested + '^{commit}').decode().strip()
    assert tested == args.tested
    for before, after in zip((B, T, R, M, BASE), (T, R, M, BASE, tested), strict=True):
        git('merge-base', '--is-ancestor', before, after)
    for path, digest in PINS.items():
        assert hashlib.sha256(raw(tested, OWN + path)[2]).hexdigest() == digest
    for revision, path, blob, digest in ORIGINALS:
        _, actual, data = raw(revision, path)
        assert actual == blob and hashlib.sha256(data).hexdigest() == digest
    # Current definitions contain the approved precise form verbatim, not a loose summary.
    original_contract = raw(BASE, CONTRACT)[2]
    contract = raw(tested, CONTRACT)[2]
    assert contract.startswith(original_contract)
    assert raw(tested, OWN + 'INITIAL_FORM.md')[2] in contract
    assert b'prospectively refines HG060' in contract
    for phrase in (b'only', b'global archival', b'Original PASS labels remain claims',
                   b'No generic success Boolean', b'prerequisite', b'storage/history',
                   b'Current candidate additions', b'first-parent3965', b'normal HG061 merge'):
        assert phrase in b' '.join(contract.split()), phrase
    matrix = contract.split(b'### HG061 required implementation decision matrix')[1].split(b'### Same HG058')[0]
    for phrase in (b'owner-neutral', b'New or modified candidate', b'Selected historical owner',
                   b'interrupted', b'unstarted', b'Status-only', b'weakened equality/all',
                   b'parser/Git bounds', b'caller role', b'No execution PASS'):
        assert phrase in matrix, phrase
    # Reversal of the exact authorized enforcement delta proves byte preservation of runtime.
    delta = json.loads(raw(tested, OWN + 'ENFORCEMENT_DELTA.json')[2])
    restored = raw(tested, VALIDATOR)[2].decode()
    for key in ('constants', 'function', 'branch', 'projection'):
        assert restored.count(delta[key]) == 1
        restored = restored.replace(delta[key], '', 1)
    assert restored.count("('HG-050', 'HG-058', 'HG-059', 'HG-060', 'HG-061')") == 1
    restored = restored.replace("('HG-050', 'HG-058', 'HG-059', 'HG-060', 'HG-061')",
                                "('HG-050', 'HG-058', 'HG-059', 'HG-060')", 1)
    assert restored.encode() == raw(BASE, VALIDATOR)[2]
    old, new = spans(raw(BASE, VALIDATOR)[2]), spans(raw(tested, VALIDATOR)[2])
    assert {name for name in old if old[name] != new.get(name)} == {'governance_allowed_patterns', 'validate'}
    assert set(new) - set(old) == {'historical_semantic_projection_errors'}
    # Every old packet byte is retained except the two expressly advanced entry triggers.
    packet_before = raw(BASE, PACKET)[2]
    packet_after = raw(tested, PACKET)[2]
    expected = packet_before.replace(b'Continuation requires actual normal HG060 merge',
                                     b'Continuation requires actual normal HG061 merge', 1)
    expected = expected.replace(b'After HG060 normal merge and resource regrant, follow',
                                b'After HG061 normal merge and resource regrant, follow', 1)
    assert packet_after.startswith(expected)
    for phrase in (b'eight declarations', b'four source callers', b'nine ordinary metadata',
                   b'semantic_validation VERIFIED/INVALID', b'acceptance_eligible false',
                   b'auditbase9700', b'first-parent3965', b'full normative positive/negative matrix'):
        assert phrase in packet_after
    allowed = {CONTRACT, PACKET, VALIDATOR, 'tests/harness/test_validator.py',
               'CURRENT_DOCUMENT_INDEX.json', 'HARNESS_DOCUMENT_MANIFEST.json',
               'docs/exec-plans/governance/HG-061.yaml'}
    changed = git('diff', '--name-only', '--no-renames', BASE, tested).decode().splitlines()
    assert all(path in allowed or path.startswith((OWN, 'docs/exec-plans/reviews/HG-061/')) for path in changed)
    # This complete path restriction preserves every historical result/report/review and all
    # source declarations, budgets/codecs/readers/controllers/frozen/product data.
    index = json.loads(raw(tested, 'CURRENT_DOCUMENT_INDEX.json')[2])
    index_before = json.loads(raw(BASE, 'CURRENT_DOCUMENT_INDEX.json')[2])
    for section in ('documents', 'machine_readable'):
        for entry in index[section]:
            assert hashlib.sha256(raw(tested, entry['path'])[2]).hexdigest() == entry['sha256']
        for entry in index_before[section]:
            entry.pop('sha256')
        for entry in index[section]:
            entry.pop('sha256')
    assert index == index_before
    manifest = json.loads(raw(tested, 'HARNESS_DOCUMENT_MANIFEST.json')[2])
    before_manifest = json.loads(raw(BASE, 'HARNESS_DOCUMENT_MANIFEST.json')[2])
    old_paths = {entry['path'] for entry in before_manifest['files']}
    assert 'docs/exec-plans/governance/HG-061.yaml' not in {entry['path'] for entry in manifest['files']}, 'mutable result must remain outside frozen delivery manifest'
    for entry in manifest['files']:
        value = raw(tested, entry['path'])[2]
        assert len(value) == entry['bytes'] and hashlib.sha256(value).hexdigest() == entry['sha256']
        assert entry['path'] in old_paths or entry['path'].startswith(OWN)
    assert old_paths <= {entry['path'] for entry in manifest['files']}
    # Independently recompute this pinned immutable research sample only. This is NOT
    # the future owner-neutral recognizer, old process replay, or production eligibility.
    record_path = 'docs/exec-plans/governance/HG-044.yaml'
    record = yaml.safe_load(raw(R, record_path)[2])
    assert record['change_identity'] == 'harness-governance-v0.1/HG-044'
    assert (record['base_commit'], record['tested_commit']) == (B, T)
    assert raw(M, record_path) == raw(tested, record_path)
    scope = [row for row in record['checks_run'] if row['check_id'] == 'scope']
    assert len(scope) == 1
    assert scope[0]['command'] == '/private/tmp/hg044-venv/bin/python docs/exec-plans/evidence/HG-044/audit.py'
    ref = scope[0]['evidence_ref']
    assert raw(M, ref) == raw(tested, ref)
    report = json.loads(raw(M, ref)[2])
    assert set(report) == {'base_commit', 'tested_commit', 'checks', 'changed', 'status', 'preserved_function_sha256'}
    assert (report['base_commit'], report['tested_commit'], report['status']) == (B, T, 'PASS')
    assert set(report['checks']) == set(NAMES) | {'scope', 'plan_prefix', 'no_instance'}
    assert all(value is True for value in report['checks'].values())
    assert set(report['preserved_function_sha256']) == set(NAMES)
    original_before, original_after = spans(raw(B, VALIDATOR)[2]), spans(raw(T, VALIDATOR)[2])
    inventory = json.loads(raw(M, ORIGINALS[6][1])[2])
    for name in NAMES:
        assert original_before[name] == original_after[name]
        assert original_after[name][0] == 'FunctionDef'
        digest = hashlib.sha256(original_after[name][1]).hexdigest()
        assert report['preserved_function_sha256'][name] == inventory['unchanged_hashes'][name] == digest
        assert name not in inventory['changed_existing'] + inventory['added']
    actual_paths = git('diff', '--name-only', '-z', '--no-renames', '--no-ext-diff', '--no-textconv', B, T).split(b'\0')[:-1]
    assert report['changed'] == [path.decode() for path in sorted(actual_paths)]
    ordinary = {'MILESTONE_CLOSURE.schema.json', VALIDATOR, 'tests/harness/test_m3_milestone_closure.py',
                'docs/harness/M3_CLOSURE_CONTRACT.md', '06_KineticLoop_Project_Plan_v0.6_HARNESS_HARDENED.md',
                'CURRENT_DOCUMENT_INDEX.json', 'HARNESS_DOCUMENT_MANIFEST.json'}
    assert all(path in ordinary or path == record_path or path.startswith((
        'docs/exec-plans/evidence/HG-044/', 'docs/exec-plans/reviews/HG-044/')) for path in report['changed'])
    plan = '06_KineticLoop_Project_Plan_v0.6_HARNESS_HARDENED.md'
    marker = '## M3 exit-evidence mapping — HG044'.encode()
    after_plan = raw(T, plan)[2]
    assert after_plan.count(marker) == 1
    assert after_plan.split(marker)[0] == raw(B, plan)[2] + b'\n'
    assert not git('ls-tree', T, '--', 'docs/exec-plans/milestones/M3.json').strip()
    limitation = ('Synthetic isolated Git fixture data is validator input only, never actual project completion evidence. '
                  'Existing canonical M1/M2/integration/provenance validator functions are byte-identical.')
    assert limitation in [value.strip() for value in record['known_limitations']]
    review = json.loads(raw(M, ORIGINALS[5][1])[2])
    assert review['reviewed_head_sha'] == R
    assert ORIGINALS[6][1] in review['evidence_refs'] and ORIGINALS[7][1] in review['evidence_refs']
    audit = json.loads(raw(M, ORIGINALS[7][1])[2])
    assert (audit['base'], audit['tested'], audit['reviewed']) == (B, T, R)
    for name in ('record_identity_revisions_status', 'path_mode_scope', 'tested_ancestry_and_suffix',
                 'no_actual_closure', 'only_legacy_function_edits_are_dispatch_scope', 'committed_plan_prefix'):
        assert audit['checks'][name] is True
    assert audit['changed_path_count'] == len(git('diff', '--name-only', '-z', B, R).split(b'\0')[:-1])
    for path in (VALIDATOR, 'docs/exec-plans/evidence/HG-044/audit.py', 'docs/harness/M3_CLOSURE_CONTRACT.md'):
        assert raw(T, path) == raw(R, path)
    print(json.dumps({'status': 'PASS', 'base': BASE, 'tested': tested, 'changed_paths': changed,
                      'approved_input_pins': PINS, 'original_blob_pins_verified': len(ORIGINALS),
                      'research_predicates_recomputed': 9, 'research_changed_paths': len(actual_paths),
                      'historical_execution': 'UNVERIFIED_MISSING_EXIT', 'acceptance_eligible': False,
                      'meaning': 'HG061 definitions/preservation only; no original execution or HG058 recognizer acceptance'}))


if __name__ == '__main__':
    main()
