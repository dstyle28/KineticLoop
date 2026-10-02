"""Independent HG043 reviewer audit; no database commands or integration writes."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile

import jsonschema
import yaml

ROOT = Path.cwd()
OUT = ROOT / 'docs/exec-plans/reviews/HG-043/final-8245480-db-raw'
BASE = '1099d85bd4aa76ec8221700e55b4e77a84479126'
HEAD = '8245480918251739339987de69bfe41fa0b39af5'
ENV = dict(os.environ, PYTHONPATH=str(ROOT / 'src'), PYTHONDONTWRITEBYTECODE='1')


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def run(name, command):
    result = subprocess.run(command, cwd=ROOT, env=ENV, capture_output=True)
    raw = result.stdout + result.stderr
    report = {'reviewed_head_sha': HEAD, 'base_commit': BASE, 'command': command,
              'exit_code': result.returncode, 'raw_sha256': hashlib.sha256(raw).hexdigest(),
              'raw_utf8': raw.decode(errors='replace')}
    (OUT / (name + '.json')).write_text(json.dumps(report, indent=2) + '\n')
    print(name, result.returncode, raw.decode(errors='replace')[-500:])
    assert result.returncode == 0


assert git('rev-parse', 'HEAD').decode().strip() == HEAD
for path in ('tools/harness/validate_harness.py', 'tests/harness/test_review_evidence_provenance.py'):
    assert (ROOT / path).read_bytes() == git('show', HEAD + ':' + path)
# Strictly audit the tested-to-reviewed governance suffix separately.
tested = '97b76c7e170368c916ca79d6c7c1656259430f30'
git('merge-base', '--is-ancestor', tested, HEAD)
for commit in git('rev-list', '--reverse', tested + '..' + HEAD).decode().splitlines():
    parents = git('rev-list', '--parents', '-n', '1', commit).decode().split()[1:]
    assert len(parents) == 1
    paths = git('diff', '--no-renames', '--name-only', '-z', parents[0], commit).decode().split('\0')[:-1]
    assert all(p.startswith('docs/exec-plans/evidence/HG-043/') or p == 'docs/exec-plans/governance/HG-043.yaml' for p in paths), paths
changed = git('diff', '--name-only', BASE, HEAD).decode().splitlines()
forbidden = ['src/', 'tests/db/', 'migrations/', '.github/', 'protocol_model/']
assert not any(p.startswith(tuple(forbidden)) for p in changed)
for p in ('05_KineticLoop_Protocol_v1.2_FROZEN.md',
          '04_KineticLoop_DB_Schema_Design_v0.2_FROZEN.md', 'FROZEN_BASELINE.json',
          'CURRENT_REQUIREMENT_SET.json', 'KineticLoop_Harness_Backlog_v0.2.json'):
    assert git('show', BASE + ':' + p) == git('show', HEAD + ':' + p)
checks = yaml.safe_load(git('show', HEAD + ':docs/exec-plans/governance/HG-043.yaml'))
check_audit = []
for check in checks['checks_run']:
    raw = git('show', HEAD + ':' + check['evidence_ref'])
    evidence = json.loads(raw)
    output = evidence['raw_utf8'].encode()
    assert evidence['tested_commit'] == checks['tested_commit']
    assert evidence['exit_code'] == 0 and evidence['result'] == 'PASS'
    assert hashlib.sha256(output).hexdigest() == evidence['raw_sha256']
    assert len(output) == evidence['raw_byte_count']
    check_audit.append({'check_id': check['check_id'], 'tested_commit': evidence['tested_commit'],
                        'raw_sha256_verified': True, 'summary': evidence['raw_utf8'][-160:]})

# Read exact committed candidate identities, then independently prove every commit
# and blob using Git rather than the implementation replay's provenance helper.
original = json.loads(git('show', HEAD + ':docs/exec-plans/evidence/HG-043/original-HG042-preflight.json'))
records = {name: candidate['record'] for name, candidate in original['candidates'].items()}
records['KL-027'] = dict(original['pending']['KL-027']['hypothetical_record_not_actual_integration'])
records['KL-027']['merge_commit'] = BASE
task_data = json.loads(git('show', BASE + ':KineticLoop_Harness_Backlog_v0.2.json'))
tasks = {task['id']: task for task in task_data['tasks']}
candidate_audit = {}
for task_id, record in sorted(records.items()):
    result_commit, reviewed, recorded, merged = (record[key] for key in
        ('result_commit', 'reviewed_head_sha', 'review_record_commit', 'merge_commit'))
    for left, right in ((result_commit, reviewed), (reviewed, recorded),
                        (recorded, merged), (merged, BASE)):
        git('merge-base', '--is-ancestor', left, right)
    parents = git('rev-list', '--parents', '-n', '1', merged).decode().split()[1:]
    assert len(parents) == 2 and recorded in parents
    suffix_commits = git('rev-list', '--reverse', reviewed + '..' + recorded).decode().splitlines()
    own_prefix = f'docs/exec-plans/reviews/{task_id}/'
    suffix = []
    for commit in suffix_commits:
        commit_parents = git('rev-list', '--parents', '-n', '1', commit).decode().split()[1:]
        assert len(commit_parents) == 1
        paths = git('diff', '--no-renames', '--name-only', '-z', commit_parents[0], commit).decode().split('\0')[:-1]
        assert all(path.startswith(own_prefix) for path in paths)
        suffix.append({'commit': commit, 'changed_paths': paths})
    results = [p for p in (f'docs/exec-plans/completed/{task_id}_RESULT.yaml',
                           f'docs/exec-plans/completed/{task_id}_RESULT.json')
               if subprocess.run(['git', 'cat-file', '-e', result_commit + ':' + p],
                                 cwd=ROOT, capture_output=True).returncode == 0]
    assert len(results) == 1
    result_bytes = git('show', result_commit + ':' + results[0])
    assert result_bytes == git('show', reviewed + ':' + results[0])
    result = yaml.safe_load(result_bytes)
    task_checks = []
    for command in result['commands_run']:
        ref = command.get('evidence_ref')
        if not ref:
            continue
        entry = git('ls-tree', '-z', reviewed, '--', ref).split(b'\0')[0]
        assert entry
        metadata, path = entry.split(b'\t', 1)
        assert metadata.split()[:2] in ([b'100644', b'blob'], [b'100755', b'blob'])
        assert path.decode() == ref
        assert git('show', reviewed + ':' + ref) == git('show', recorded + ':' + ref)
        task_checks.append({'check_id': command['check_id'], 'result': command['result'],
                            'evidence_ref': ref, 'regular_blob_at_reviewed': True,
                            'unchanged_to_review_record': True})
    review_refs = []
    for kind in tasks[task_id]['review_requirements']:
        review_path = own_prefix + kind + '.json'
        review = json.loads(git('show', recorded + ':' + review_path))
        assert review['reviewed_head_sha'] == reviewed and review['status'] == 'PASS'
        for ref in review.get('evidence_refs', []):
            at_reviewed = git('ls-tree', '-z', reviewed, '--', ref).split(b'\0')[0]
            source = reviewed if at_reviewed else recorded
            if not at_reviewed:
                assert ref.startswith(own_prefix)
            entry = git('ls-tree', '-z', source, '--', ref).split(b'\0')[0]
            metadata, path = entry.split(b'\t', 1)
            assert metadata.split()[:2] in ([b'100644', b'blob'], [b'100755', b'blob'])
            assert path.decode() == ref
            assert git('show', source + ':' + ref) == git('show', merged + ':' + ref)
            detail = {'review_type': kind, 'path': ref, 'bound_source': source,
                      'regular_git_entry': metadata.decode(), 'blob_sha256': hashlib.sha256(git('show', source + ':' + ref)).hexdigest(), 'review_created': not bool(at_reviewed)}
            if not at_reviewed:
                # Reviewer-created DB runs are classified separately from task checks.
                blob = git('show', source + ':' + ref)
                detail['raw_preview'] = blob.decode(errors='replace')[:800]
            review_refs.append(detail)
    candidate_audit[task_id] = {'record': record, 'normal_merge_parents': parents,
                                'strict_own_linear_suffix': suffix,
                                'result_bytes_unchanged': True,
                                'pre_review_task_checks': task_checks,
                                'review_refs': review_refs}

(OUT / 'git-static-candidates.json').write_text(json.dumps({
    'reviewed_head_sha': HEAD, 'base_commit': BASE, 'changed_paths': changed,
    'db_application_migration_ci_frozen_requirement_backlog_change': False,
    'governance_check_evidence': check_audit, 'candidates': candidate_audit,
    'classification': 'Review-created DB logs are independent reviewer runs; all task check refs exist unchanged at reviewed SHA. No DB/product/requirement PASS inferred.'
}, indent=2) + '\n')

python = str(ROOT / '.venv/bin/python')
run('provenance-regressions', [python, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
    'tests/harness/test_review_evidence_provenance.py'])
run('diff-check', ['git', 'diff', '--check', BASE, HEAD])
