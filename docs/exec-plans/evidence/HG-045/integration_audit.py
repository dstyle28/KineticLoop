"""Verify actual immutable task integration chains and prerequisites, without edits."""
import hashlib
import json
import subprocess
from pathlib import Path

from jsonschema import Draft202012Validator

from tools.harness.validate_harness import integration_record_errors

root = Path.cwd()
base = '26906bd7f4444914c228e98377f2b164fee0dd5d'
tasks = {t['id']: t for t in json.loads((root/'KineticLoop_Harness_Backlog_v0.2.json').read_text())['tasks']}
schemas = [Draft202012Validator(json.loads((root/p).read_text())) for p in (
    'INTEGRATION_RECORD.schema.json', 'THREAD_RESULT.schema.json', 'THREAD_REVIEW.schema.json')]
expected = {'KL-028': ('9268fc8dd8c071c02dc5c698274dbf6fcd112776',
                       'debd5e58f98b4b20a2dd1ae132799d2373797622'),
            'KL-029': ('9268fc8dd8c071c02dc5c698274dbf6fcd112776',
                       'b9fbf9b475e07765db62e67f0104a800036dda4d')}
rows = []
for name in ['KL-028','KL-029','KL-076','KL-079','KL-077','KL-027','KL-078','KL-026','KL-023','KL-022']:
    path = root/'docs/exec-plans/integrations'/f'{name}.json'
    record = json.loads(path.read_text())
    errors = integration_record_errors(root, path, record, *schemas, tasks)
    assert not errors, (name, errors)
    row = dict(task=name, integration=record, semantic_errors=errors)
    if name in expected:
        result_path = f'docs/exec-plans/completed/{name}_RESULT.yaml'
        result_bytes = subprocess.check_output(['git','show',record['result_commit']+':'+result_path])
        import yaml
        result = yaml.safe_load(result_bytes)
        assert (result['base_commit'],result['tested_commit']) == expected[name]
        assert result['integration_status'] == 'UNMERGED' and result.get('merge_commit') is None
        chain = [*expected[name],record['result_commit'],record['reviewed_head_sha'],
                 record['review_record_commit'],record['merge_commit'],base]
        edges = []
        for before,after in zip(chain,chain[1:]):
            run = subprocess.run(['git','merge-base','--is-ancestor',before,after])
            assert run.returncode == 0
            edges.append(dict(before=before,after=after,is_ancestor=True))
        suffix = subprocess.check_output(['git','rev-list','--reverse',record['reviewed_head_sha']+'..'+record['review_record_commit']],text=True).splitlines()
        suffix_paths = {}
        for sha in suffix:
            assert len(subprocess.check_output(['git','rev-list','--parents','-n','1',sha],text=True).split()) == 2
            changed = subprocess.check_output(['git','diff-tree','--no-commit-id','--name-only','-r',sha],text=True).splitlines()
            assert changed and all(p.startswith(f'docs/exec-plans/reviews/{name}/') for p in changed)
            suffix_paths[sha] = changed
        for revision in [record['reviewed_head_sha'],record['review_record_commit'],record['merge_commit']]:
            assert subprocess.check_output(['git','show',revision+':'+result_path]) == result_bytes
        parents = subprocess.check_output(['git','rev-list','--parents','-n','1',record['merge_commit']],text=True).split()[1:]
        assert len(parents) == 2 and record['review_record_commit'] in parents
        row.update(edges=edges,review_record_only_suffix=suffix_paths,normal_merge_parents=parents,
                   immutable_result_sha256=hashlib.sha256(result_bytes).hexdigest(),historical_result_status='UNMERGED')
    rows.append(row)
print(json.dumps(dict(protected_base=base,rows=rows),indent=2))
