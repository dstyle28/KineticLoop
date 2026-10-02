"""Verify actual normal merge/result/review ancestry, then append five integrations."""
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import jsonschema

ROOT = Path.cwd()
BASE = '93b38f20a3f3d71206515fb0f4d852f5b0b6d344'
HERE = ROOT / 'docs/exec-plans/evidence/HG-042'
spec = importlib.util.spec_from_file_location('integration_validator', ROOT / 'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
schemas = [jsonschema.Draft202012Validator(json.loads((ROOT / p).read_text())) for p in
           ('INTEGRATION_RECORD.schema.json', 'THREAD_RESULT.schema.json', 'THREAD_REVIEW.schema.json')]
tasks = {t['id']: t for t in json.loads((ROOT / v.BACKLOG).read_text())['tasks']}
merges = {'KL-075': 'd0470ba', 'KL-076': '035644e', 'KL-077': '6d1348c',
          'KL-079': '7be0449', 'KL-027': '1099d85'}
report = {'protected_base': BASE, 'head': v.resolve(ROOT, 'HEAD'), 'candidates': {}}
for task_id, short in merges.items():
    merged = v.resolve(ROOT, short)
    assert v.is_ancestor(ROOT, merged, BASE)
    parents = v.git(ROOT, 'rev-list', '--parents', '-n', '1', merged).decode().split()[1:]
    assert len(parents) == 2
    review_commit = parents[1]
    reviews = [json.loads(v.git(ROOT, 'show', review_commit +
                f':docs/exec-plans/reviews/{task_id}/{kind}.json'))
               for kind in tasks[task_id]['review_requirements']]
    reviewed_heads = {r['reviewed_head_sha'] for r in reviews}
    assert len(reviewed_heads) == 1
    reviewed = v.resolve(ROOT, reviewed_heads.pop())
    assert all(r['status'] == 'PASS' and r['task_identity'] == tasks[task_id]['task_identity'] for r in reviews)
    record = {'task_identity': tasks[task_id]['task_identity'], 'display_task_id': task_id,
              'result_commit': reviewed, 'reviewed_head_sha': reviewed,
              'review_record_commit': review_commit, 'merge_commit': merged,
              'integration_status': 'MERGED'}
    errors = v.integration_record_errors(ROOT, Path(task_id + '.json'), record, *schemas, tasks)
    assert not errors, (task_id, errors)
    result_path = v.result_paths_at_revision(ROOT, task_id, reviewed)
    assert len(result_path) == 1
    raw = v.git(ROOT, 'show', reviewed + ':' + result_path[0])
    assert raw == v.git(ROOT, 'show', merged + ':' + result_path[0])
    result = v.load_artifact_text(raw.decode(), Path(result_path[0]).suffix)
    assert result['integration_status'] == 'UNMERGED'  # Historical result is not rewritten.
    suffix = v.suffix_errors(ROOT, reviewed, review_commit, task_id, 'review')
    assert not suffix
    refs = []
    for review in reviews:
        for ref in review['evidence_refs']:
            at_reviewed = v.revision_regular_file(ROOT, ref, reviewed)
            assert v.review_evidence_exists(ROOT, ref, reviewed, review_commit, task_id, True)
            source = reviewed if at_reviewed else review_commit
            refs.append({'review_type': review['review_type'], 'path': ref,
                         'source_revision': source,
                         'binding': 'REVIEWED' if at_reviewed else 'PROVEN_REVIEW_RECORD_ONLY',
                         'git_entry': v.git(ROOT, 'ls-tree', source, '--', ref).decode().strip()})
    report['candidates'][task_id] = {'record': record, 'normal_merge_parents': parents,
        'validator_errors': errors, 'strict_review_suffix_errors': suffix,
        'result_path': result_path[0], 'result_sha256': hashlib.sha256(raw).hexdigest(),
        'historical_result_integration_status': result['integration_status'], 'references': refs}
if '--write' in sys.argv:
    for task_id, item in report['candidates'].items():
        path = ROOT / f'docs/exec-plans/integrations/{task_id}.json'
        assert not path.exists()
        path.write_text(json.dumps(item['record'], indent=2) + '\n')
    (HERE / 'integration-provenance.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
