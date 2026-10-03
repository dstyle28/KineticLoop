"""Separate security-boundary review; exact Git inputs, no credentials or DB use."""
import copy
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / 'tools/harness'))
import compact_evidence as ce
import validate_harness as v

HEAD = 'ceed78db431a348aae0b599a5e1b09bb082fb968'
BASE = '95ddd75d3eb410b7dffa15a1017276c504adc9a6'
TESTED = '4db695230c2158f67394c8ac79a5f0fdf511849a'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def blob(path, revision=HEAD):
    return ce.blob(ROOT, path, revision)


def main():
    assert git('rev-parse', 'HEAD').decode().strip() == HEAD
    changed = git('diff', '--name-only', BASE, HEAD).decode().splitlines()
    assert all(v.matches(p, v.governance_allowed_patterns('HG-049')) for p in changed)
    assert not any(p.startswith(('src/', 'tests/db/', '.github/', 'migrations/')) for p in changed)
    index = json.loads(blob(v.INDEX))
    for entry in index['documents'] + index['machine_readable']:
        assert ce.digest(blob(entry['path'])) == entry['sha256']
    protected = {e['path'] for e in json.loads(blob('FROZEN_BASELINE.json', BASE))['files']}
    protected.update({'FROZEN_BASELINE.json', 'CURRENT_REQUIREMENT_SET.json',
                      '12_KineticLoop_Integration_Spec_v0.1.md', 'THREAD_REVIEW.schema.json',
                      'docs/harness/MERGE_GATE.md', 'docs/harness/EVIDENCE_STORAGE_POLICY.md',
                      'docs/harness/HARNESS_GOVERNANCE_CONTRACT.md',
                      'docs/harness/THREAD_REVIEW_CONTRACT.md'})
    for path in protected:
        assert blob(path) == blob(path, BASE)
    previous = json.loads(blob(v.BACKLOG, BASE))
    current = json.loads(blob(v.BACKLOG))
    task = next(t for t in current['tasks'] if t['id'] == 'KL-080')
    expected = copy.deepcopy(previous)
    target = next(t for t in expected['tasks'] if t['id'] == 'KL-080')
    target['check_contracts'][7]['pass_oracle'] = task['check_contracts'][7]['pass_oracle']
    target['deliverables'][1] = task['deliverables'][1]
    assert expected == current
    assert task['status'] == 'NOT_STARTED' and task['requirements_covered'] == []
    assert task['evidence_refs'] == [] and len(task['review_requirements']) == 4
    oracle = task['check_contracts'][7]['pass_oracle']
    for clause in ['actual kl079-full-actions-v1 F/D/N owners', 'for both action members',
                   'exact current member bindings', 'positive through COMMIT_READY',
                   'untouched owner-produced mechanical S37', 'authenticated current ingress',
                   'correct policy, closure, owner, request, attempt, fence, lease, epoch',
                   'execution basis, key and fingerprint', 'actual legacy dependency/certificate consumer',
                   'complete zero effects, including first-use head rollback', 'exact reached guard',
                   'request construction, registration, unrelated ingress/lifecycle/hash errors',
                   'full-policy downgrade are insufficient substitutes', 'No target seeding, caller PASS',
                   'certificate rewriting', 'production or real-data-shadow output']:
        assert clause in oracle
    source_paths = ['src/kineticloop/protocol/execution.py',
                    'src/kineticloop/persistence/protocol_execution.py',
                    'src/kineticloop/persistence/transactions.py',
                    'src/kineticloop/persistence/deterministic_planning.py',
                    'docs/contracts/deterministic_planning.md',
                    'docs/contracts/full_action_preparation.md',
                    'docs/contracts/full_test_execution.md',
                    'docs/contracts/protocol_execution.md']
    hashes = {}
    for path in source_paths:
        raw = blob(path)
        assert raw == blob(path, BASE)
        hashes[path] = ce.digest(raw)
    identity, adapter, tx, producer = [blob(p).decode() for p in source_paths[:4]]
    assert 'self.actor.role != ActorRole.TEST' in identity
    assert 'command_digest(command) != command.request_hash' in identity
    assert 'scope.policy_id != str(self.policy_id)' in identity
    assert 'scope.environment_id != str(self.environment_id)' in identity
    assert 'command.expected_owner_id != self.actor.identity_id' in identity
    assert 'self._identity.require_wire(command)' in adapter
    assert 'self._guard(UUID(command.subject_id))' in adapter
    assert 'tx.require_test_execution_ingress(' in adapter
    assert 'row[:4] != ("TEST", policy_id, environment_id, principal)' in tx
    assert 'row[4] != row[5] or row[5] == principal' in tx
    assert 'active_policy_bundle_id") != policy_id' in tx
    assert 'ref_s34_id=UUID(request.sources["nutrition"]["id"])' in producer
    assert 'ref_s34_id=UUID(payload["fitness_id"])' in producer
    assert '(demand_basis[2] != demand_basis[3] and not self._coordination_context.get("full_execution_members"))' in tx
    assert 'demand_basis[1] != demand_basis[5]' in tx
    assert tx.index('policy, demand, and calendar authorization bounds must exist') < tx.index('certificate != expected_certificate')
    assert 'legacy downgrade denied' in tx
    assert 'tx.lock_daily_head(inputs[0], create_first=True)' in adapter
    assert 'with connection.transaction():\n        transaction = RepositoryTransaction' in tx
    assert 'result = operation(transaction)\n        transaction.finish()\n        return result' in tx
    assert '"executable": False' in adapter
    assert 'e["command_authority"] != "NONE"' in producer
    assert 'f["fact_kind"] != "WORKOUT_ACTUAL"' in producer
    assert 'a["ref_s05_id"] != str(identity.policy_id)' in producer
    budget = ce.audit(ROOT, BASE, HEAD, 'HG-049')
    assert budget['errors'] == [], budget
    assert budget['stored_bytes'] <= ce.TOTAL_LIMIT
    evidence_prefix = 'docs/exec-plans/evidence/HG-049/'
    evidence_rows = []
    secret_patterns = [rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
                       rb'AKIA[A-Z0-9]{16}', rb'gh[pousr]_[A-Za-z0-9]{36,}']
    tree = set(git('ls-tree', '-r', '--name-only', HEAD).decode().splitlines())
    for path in sorted(p for p in tree if p.startswith(evidence_prefix) and not p.endswith('.gz')):
        data = blob(path)
        envelope = ce.envelope(data)
        raw = ce.read(ROOT, path, HEAD) if envelope is not None else data
        assert not any(re.search(pattern, raw) for pattern in secret_patterns), ('credential-candidate', path)
        evidence_rows.append({'path': path, 'blob_sha256': ce.digest(data),
                              'decoded_sha256': ce.digest(raw), 'decoded_bytes': len(raw),
                              'exit_code': envelope['exit_code'] if envelope else None})
    record_path = ROOT / 'docs/exec-plans/governance/HG-049.yaml'
    assert record_path.read_bytes() == blob(str(record_path.relative_to(ROOT)))
    record = v.load_artifact(record_path)
    assert record['tested_commit'] == TESTED and record['base_commit'] == BASE
    assert record['frozen_impact'] == 'NONE' and record['authority_entries_added'] == []
    assert len(record['checks_run']) == 7
    for check in record['checks_run']:
        assert check['result'] == 'PASS'
        raw = ce.read(ROOT, check['evidence_ref'], HEAD, tested=TESTED,
                      command=check['command'], exit_code=0)
        assert raw is not None
    assert not v.governance_suffix_errors(ROOT, TESTED, HEAD, 'HG-049', 'tested')
    d = evidence_prefix + 'checks-4db6952/'
    run = json.loads(ce.read(ROOT, d + 'harness-execution-json.json', HEAD))
    assert run['exit_code'] == 0 and run['errors'] == []
    assert all(report['outcome'] == 'passed' for report in run['reports'])
    calls = [r for r in run['reports'] if r['phase'] == 'call']
    assert len(calls) == 1347 and len({r['nodeid'] for r in calls}) == 1347
    xml = ET.fromstring(ce.read(ROOT, d + 'harness-junit-xml.json', HEAD))
    assert len(list(xml.iter('testcase'))) == 1347
    assert not list(xml.iter('failure')) and not list(xml.iter('error')) and not list(xml.iter('skipped'))
    assert b'241 passed' in ce.read(ROOT, d + 'unit.json', HEAD)
    historical = [p for p in git('ls-tree', '-r', '--name-only', BASE).decode().splitlines()
                  if p.startswith(('docs/history/', 'docs/exec-plans/completed/',
                                   'docs/exec-plans/reviews/', 'docs/exec-plans/evidence/',
                                   'docs/exec-plans/integrations/', 'docs/exec-plans/milestones/'))]
    assert not set(historical).intersection(changed)
    preserved_protocol = {}
    for p in sorted((ROOT / 'docs/exec-plans/reviews/HG-049/protocol').glob('*')):
        if p.is_file():
            preserved_protocol[str(p.relative_to(ROOT))] = ce.digest(p.read_bytes())
    p = ROOT / 'docs/exec-plans/reviews/HG-049/PROTOCOL.json'
    preserved_protocol[str(p.relative_to(ROOT))] = ce.digest(p.read_bytes())
    print(json.dumps({'status': 'PASS', 'review_type': 'SECURITY_DATA_BOUNDARY',
                      'reviewed_head_sha': HEAD, 'base_commit': BASE, 'tested_commit': TESTED,
                      'source_hashes': hashes, 'evidence_budget': budget,
                      'decoded_evidence': evidence_rows, 'preserved_history_paths': len(historical),
                      'prior_protocol_bytes_sha256': preserved_protocol,
                      'harness_passed': 1347, 'unit_passed': 241,
                      'credential_scan': 'No private-key, AWS-access-key or GitHub-token candidate in new decoded evidence',
                      'limitations': 'Static source/governance review, no DB guard execution; exact-head hosted/App/fullDB gates pending'}, indent=2))


if __name__ == '__main__':
    main()
