"""Replay five actual protected-ancestry integrations in an ephemeral clone, never official records."""
import hashlib
import importlib.util
import json
import subprocess
import tempfile
import types
from pathlib import Path

import jsonschema

ROOT = Path.cwd()
BASE = '1099d85bd4aa76ec8221700e55b4e77a84479126'
HERE = ROOT / 'docs/exec-plans/evidence/HG-043'
original = json.loads((HERE / 'original-HG042-preflight.json').read_text())
records = {key: value['record'] for key, value in original['candidates'].items()}
record = dict(original['pending']['KL-027']['hypothetical_record_not_actual_integration'])
record['merge_commit'] = BASE  # PR83 has now actually normally merged; verify ancestry below.
records['KL-027'] = record
source = subprocess.check_output(['git', 'show', BASE + ':tools/harness/validate_harness.py'])
old = types.ModuleType('protected_validator')
old.__file__ = str(ROOT / 'tools/harness/validate_harness.py')
exec(compile(source, old.__file__, 'exec'), old.__dict__)
spec = importlib.util.spec_from_file_location('candidate_validator', ROOT / 'tools/harness/validate_harness.py')
assert spec and spec.loader
new = importlib.util.module_from_spec(spec)
spec.loader.exec_module(new)
report = {'protected_base': BASE, 'original_audit_sha256': hashlib.sha256(
    (HERE / 'original-HG042-preflight.json').read_bytes()).hexdigest(),
    'purpose': 'Provenance replay only; no official integration writes or product/test PASS claims.',
    'candidates': {}}
with tempfile.TemporaryDirectory(prefix='hg043-protected-replay-') as temp:
    fixture = Path(temp) / 'repo'
    subprocess.run(['git', 'clone', '--shared', '--no-checkout', '-q', str(ROOT), str(fixture)], check=True)
    subprocess.run(['git', 'checkout', '-q', '--detach', BASE], cwd=fixture, check=True)
    schemas = [jsonschema.Draft202012Validator(json.loads((fixture / path).read_text()))
               for path in ('INTEGRATION_RECORD.schema.json', 'THREAD_RESULT.schema.json',
                            'THREAD_REVIEW.schema.json')]
    tasks = {t['id']: t for t in json.loads((fixture / new.BACKLOG).read_text())['tasks']}
    for task_id, record in sorted(records.items()):
        reviewed, review_commit, merged = (record[key] for key in
            ('reviewed_head_sha', 'review_record_commit', 'merge_commit'))
        assert new.is_ancestor(fixture, merged, BASE)
        assert new.is_ancestor(fixture, reviewed, review_commit)
        assert new.is_ancestor(fixture, review_commit, merged)
        suffix = new.suffix_errors(fixture, reviewed, review_commit, task_id, 'review')
        assert not suffix, suffix
        parents = new.git(fixture, 'rev-list', '--parents', '-n', '1', merged).decode().split()[1:]
        assert len(parents) == 2 and review_commit in parents, (task_id, parents)
        before = old.integration_record_errors(fixture, Path(task_id + '.json'), record, *schemas, tasks)
        after = new.integration_record_errors(fixture, Path(task_id + '.json'), record, *schemas, tasks)
        refs = []
        for kind in tasks[task_id]['review_requirements']:
            review = json.loads(new.git(fixture, 'show', review_commit +
                f':docs/exec-plans/reviews/{task_id}/{kind}.json'))
            for ref in review.get('evidence_refs', []):
                refs.append({'review_type': kind, 'path': ref,
                    'at_reviewed': new.revision_regular_file(fixture, ref, reviewed),
                    'review_commit_entry': new.git(fixture, 'ls-tree', '-z', review_commit, '--', ref).decode(),
                    'merge_entry': new.git(fixture, 'ls-tree', '-z', merged, '--', ref).decode(),
                    'first_add_commits': new.git(fixture, 'log', '--reverse', '--diff-filter=A',
                                                '--format=%H', review_commit, '--', ref).decode().splitlines()})
        report['candidates'][task_id] = {'record': record, 'normal_merge_parents': parents,
            'original_validator_errors': before, 'repaired_validator_errors': after,
            'strict_review_suffix_errors': suffix, 'references': refs}
        assert len(before) == {'KL-075': 3, 'KL-076': 1, 'KL-027': 18, 'KL-077': 0, 'KL-079': 0}[task_id], before
        assert all(e.startswith('integration-review-evidence:') for e in before), before
        assert not after, after
print(json.dumps(report, indent=2))
