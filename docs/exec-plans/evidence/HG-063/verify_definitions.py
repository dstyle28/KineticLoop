"""HG063 portable definition checks. Historical Git objects are data, never executed."""
import argparse
import ast
import hashlib
import json
import subprocess
import sys
import unittest
from functools import lru_cache
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
BASE = '161744c5760561349bdeb17d628e38220640c95b'
sys.path.insert(0, str(ROOT))
from tools.harness import validate_harness as validator
from definition_binding_package import load_binding_package
from definition_data import strict_json
from fixture_support import CATALOG, ROLES, ROWS, case


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(name):
    return json.loads((HERE / name).read_text())


@lru_cache(maxsize=8192)
def git(*args):
    proc = subprocess.run(['git', *args], cwd=ROOT, capture_output=True, timeout=30)
    assert proc.returncode == 0, (args, proc.returncode, proc.stderr[:500])
    assert len(proc.stdout) <= 8 * 1024 * 1024, args
    return proc.stdout


def ancestor(a, b, expected=0):
    proc = subprocess.run(['git', 'merge-base', '--is-ancestor', a, b], cwd=ROOT,
                          capture_output=True, timeout=30)
    assert type(proc.returncode) is int and proc.returncode == expected, (a, b, proc.returncode)


def blob(rev, path):
    entry = git('ls-tree', '-z', rev, '--', path).split(b'\0')
    assert len(entry) == 2 and not entry[-1], (rev, path)
    mode, kind, rest = entry[0].split(b' ', 2)
    oid, found = rest.split(b'\t', 1)
    assert mode in (b'100644', b'100755') and kind == b'blob' and found.decode() == path
    size = int(git('cat-file', '-s', oid.decode()))
    assert size <= 4 * 1024 * 1024
    raw = git('cat-file', 'blob', oid.decode())
    assert len(raw) == size
    return raw, dict(mode=mode.decode(), blob=oid.decode(), bytes=size, sha256=sha(raw))


def verify_pins():
    provenance = read('DELIVERY_PROVENANCE.json')
    assert provenance['source_manifest']['sha256'] == '830c545b077fbf121b50b658f826578a8c7a226cc55fda3362c5d8a266fb91bc'
    source = read('PREPARATION_MANIFEST.json')
    assert sha((HERE / 'PREPARATION_MANIFEST.json').read_bytes()) == provenance['source_manifest']['sha256']
    source_pins = {Path(p['path']).name: p for p in source['files']}
    for item in provenance['files']:
        raw = (HERE / item['delivery']).read_bytes()
        assert dict(bytes=len(raw), sha256=sha(raw)) == item['delivery_identity']
        assert item['source_identity'] == {k: source_pins[item['delivery']][k] for k in ('bytes', 'sha256')}
        restored = raw.decode()
        for delta in reversed(item.get('exact_replacements', [])):
            assert restored.count(delta['after']) == 1
            restored = restored.replace(delta['after'], delta['before'])
        assert dict(bytes=len(restored.encode()), sha256=sha(restored.encode())) == item['source_identity']
    assert sha((HERE / 'PACKET.md').read_bytes()) == '572867a8963ec4d3b143f5dc15a11aca385b491c47f37133dde8ed98747b79f8'
    binding = load_binding_package(HERE)
    package = read('BINDING_PACKAGE.json')
    assert package['source']['sha256'] == 'e102d0931a34567cdd44b8910927750e364c9e85f4ebf6c78177332daddb9b47'
    assert sha(json.dumps(binding, sort_keys=True, separators=(',', ':')).encode()) == provenance['decoded_canonical_sha256']
    assert provenance['decoded_identity_preflight']['original_equal_delivered_decoded'] is True
    assert len(binding['rows']) == 39
    return binding


def verify_git_bindings(binding):
    observations = []
    for row, research in zip(binding['rows'], ROWS['rows'], strict=True):
        assert row['row'] == research['row'] and row['owner'] == research['owner']
        for pin in row['pins'] + row['indexed_authorities']:
            _, actual = blob(pin['revision'], pin['path'])
            assert actual == {k: pin[k] for k in actual}, (row['row'], pin)
        owner = row['owner'].split('/')[-1]
        path = 'docs/exec-plans/governance/' + owner + '.yaml'
        current, _ = blob(row['C'], path)
        original, _ = blob(row['L'], path)
        assert current == original
        record = yaml.safe_load(current)
        assert (record['change_identity'], record['base_commit'], record['tested_commit']) == (row['owner'], row['B'], row['T'])
        assert [x for x in record['checks_run'] if x['evidence_ref'] == row['ref']] == research['checks']
        report, identity = blob(row['C'], row['ref'])
        assert report == blob(row['L'], row['ref'])[0]
        assert identity == {k: research['report_identity'][k] for k in identity}
        for duty in row['original_review_duties']:
            rev = duty['revision']
            index = json.loads(blob(rev, 'CURRENT_DOCUMENT_INDEX.json')[0])
            entries = index['documents'] + index['machine_readable']
            for pin in (p for p in row['indexed_authorities'] if p['revision'] == rev and p['path'] != 'CURRENT_DOCUMENT_INDEX.json'):
                assert any(x['path'] == pin['path'] and x['sha256'] == pin['sha256'] for x in entries)
            contract = blob(rev, 'docs/harness/HARNESS_GOVERNANCE_CONTRACT.md')[0]
            assert sha(contract) == duty['contract_sha256'] and duty['GENERAL_required'] is True
            assert b'GENERAL' in contract
            schema = json.loads(blob(rev, 'HARNESS_CHANGE.schema.json')[0])
            jsonschema.validate(record, schema)
        ancestor(row['B'], row['T'])
        ancestor(row['B'], row['L'])
        ancestor(row['L'], row['C'])
        if row['lineage_gap']:
            gap = row['lineage_gap']
            assert type(gap['observed_ancestry_exit']) is int and gap['observed_ancestry_exit'] == 1
            assert gap['tested_delivery_ancestor'] is False and row['R'] is None
            ancestor(row['T'], row['L'], 1)
            for field in ('tested_object', 'delivery_object'):
                obj = gap[field]
                assert git('show', '-s', '--format=%T', obj['revision']).decode().strip() == obj['tree']
                assert git('show', '-s', '--format=%P', obj['revision']).decode().split() == obj['parents']
            assert row['missing_review_absence']
            for absence in row['missing_review_absence']:
                assert git('ls-tree', '-z', absence['revision'], '--', absence['canonical_path']) == b''
                assert absence['entry_count'] == 0 and absence['regular_tree_lookup_completed'] is True
        else:
            ancestor(row['T'], row['R']); ancestor(row['R'], row['L'])
            assert blob(row['R'], path)[0] == current
            review = json.loads(blob(row['L'], 'docs/exec-plans/reviews/' + owner + '/GENERAL.json')[0])
            assert review['task_identity'] == row['owner'] and review['reviewed_head_sha'] == row['R']
            assert row['ref'] in review['evidence_refs'] or (row['review_reference_kind'] == 'ONE_CANONICAL_RECORD_HOP' and path in review['evidence_refs'])
            jsonschema.validate(review, json.loads(blob(row['L'], 'THREAD_REVIEW.schema.json')[0]))
        if row['producer_attribution']:
            producer = row['producer_attribution']['Z']
            assert git('show', '-s', '--format=%P', row['R']).decode().split() == [producer]
            ancestor(row['T'], producer)
            assert git('ls-tree', '-z', producer, '--', row['ref']) == b''
            before = yaml.safe_load(blob(producer, path)[0]); after = dict(record)
            after['checks_run'] = [x for x in after['checks_run'] if x['evidence_ref'] != row['ref']]
            after['files_changed'] = [x for x in after['files_changed'] if x != row['ref']]
            assert before == after
        if research['disposition'] != 'KEEP_NATIVE_CAPTURE_PATH':
            profile = next(p for p in CATALOG['profiles'] if p['profile'] == research['grammar'])
            reconstructed, _, _, _ = case(profile)
            assert reconstructed == report
        else:
            for observed in research['exit_observations']:
                index_pin = observed['index']
                index_raw, index_identity = blob(row['C'], index_pin['path'])
                assert all(index_identity[k] == index_pin[k] for k in ('blob', 'bytes', 'sha256'))
                assert index_raw == blob(row['L'], index_pin['path'])[0]
                native_index = strict_json(index_raw)
                assert native_index['base_commit'] == row['B'] and native_index['tested_commit'] == row['T']
                assert observed['check'] in native_index['checks'], (row['row'], observed['check'], native_index['checks'])
                assert index_pin['path'] in record['files_changed']
                assert index_pin['path'] in review['evidence_refs']
                assert observed['check']['exit_code'] == 0 and type(observed['check']['exit_code']) is int
                assert observed['check']['stdout_sha256'] == sha(report)
                assert all(observed['binding_checks'].values())
        observations.append(dict(row=row['row'],owner=row['owner'],report_sha256=sha(report),lineage_gap=bool(row['lineage_gap']),review_certified=False))
    assert sum(x['lineage_gap'] for x in observations) == 1
    print(json.dumps(dict(original_binding_count=39,observations=observations),sort_keys=True))


def verify_scope(tested, preflight):
    if not preflight:
        assert git('rev-parse', 'HEAD').decode().strip() == tested
        ancestor(BASE, tested)
    changed = git('diff', '--name-only', BASE, tested if not preflight else '--').decode().splitlines()
    assert all(validator.matches(p, validator.HG063_ALLOWED_PATTERNS) for p in changed), changed
    for path in ('docs/harness/HARNESS_GOVERNANCE_CONTRACT.md', 'docs/exec-plans/active/HG-058.md'):
        old = git('show', BASE + ':' + path).decode()
        current = (ROOT / path).read_text()
        if path.endswith('HG-058.md'):
            old = old.replace('Continuation requires actual normal HG062 merge and coordinator resource regrant.', 'Continuation requires actual normal HG063 merge, complete installed readiness and root resource regrant.')
        assert current.startswith(old + '\n\n## HG063 ')
    frozen = ['CURRENT_REQUIREMENT_SET.json', 'FROZEN_BASELINE.json', 'HARNESS_CHANGE.schema.json', 'THREAD_REVIEW.schema.json', 'tools/harness/compact_evidence.py','tools/harness/local_gate.py','docs/harness/THREAD_REVIEW_CONTRACT.md','docs/harness/EVIDENCE_STORAGE_POLICY.md']
    frozen += [e['path'] for e in json.loads(git('show', BASE + ':CURRENT_DOCUMENT_INDEX.json'))['documents'] if e['status'] == 'FROZEN']
    for path in frozen:
        assert (ROOT / path).read_bytes() == git('show', BASE + ':' + path)
    # Existing validator functions remain identical except literal own-task dispatch/review branches.
    def functions(raw):
        tree=ast.parse(raw);return {n.name:ast.dump(n,include_attributes=False) for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
    old=functions(git('show',BASE+':tools/harness/validate_harness.py'));new=functions((ROOT/'tools/harness/validate_harness.py').read_bytes())
    changed_functions={name for name in old if old[name]!=new[name]}
    assert changed_functions <= {'governance_allowed_patterns','validate','main'}, changed_functions
    assert set(new)-set(old)=={'plain_archival_projection_errors'}
    files=[p for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    assert all(p.stat().st_size<=262144 for p in files)
    assert sum(p.stat().st_size for p in files)<=16*1024*1024
    assert len(CATALOG['profiles'])==33 and len(ROLES['profiles'])==33
    print(json.dumps(dict(scope='HG063_ONLY',changed_functions=sorted(changed_functions),plain_files=len(files),bytes=sum(p.stat().st_size for p in files))))


def flatten(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from flatten(test)
        else:
            yield test


def run_fixtures():
    suite=unittest.defaultTestLoader.discover(str(HERE),pattern='test_*.py')
    ids=[t.id() for t in flatten(suite)]
    assert len(ids)==len(set(ids))==255 and sorted(ids)==read('FIXTURE_IDENTITIES.json')['identities']
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    assert result.testsRun==255 and not result.skipped and not result.expectedFailures and not result.unexpectedSuccesses
    assert result.wasSuccessful()
    print(json.dumps(dict(fixture_count=255,positive_identities=sorted(ids),execution='FRESH_HG063_DEFINITION_ONLY')))


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--base',required=True);parser.add_argument('--tested',required=True);parser.add_argument('--preflight',action='store_true');args=parser.parse_args()
    assert args.base==BASE
    binding=verify_pins();verify_scope(args.tested,args.preflight);verify_git_bindings(binding)
    if not args.preflight:run_fixtures()
    print('HG063 definitions PASS; no historical execution/review/acceptance certification')
