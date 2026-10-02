"""Persist exact-SHA review evidence after independent audit/probe success."""
import hashlib
import json
from pathlib import Path
import jsonschema

root=Path.cwd(); prefix='docs/exec-plans/reviews/HG-044/PROTOCOL-r5-raw'
out=root/prefix
assert json.loads((out/'audit.json').read_text())['status']=='PASS'
assert json.loads((out/'probe.json').read_text())['status']=='PASS'
evidence=[prefix+'/'+name for name in ('assessment.md','audit.py','audit.json','complete-diff.patch',
          'probe.py','probe.json','genuine-collection.stdout.log','genuine-collection.stderr.log',
          'genuine-execution.stdout.log','genuine-execution.stderr.log','genuine-junit.xml',
          'probe-case/tests/unit/test_parameter.py','broad-diff.json','broad-diff.stdout.log',
          'broad-diff.stderr.log','source-diff.log','finalize.py')]
evidence += ['docs/exec-plans/governance/HG-044.yaml','docs/harness/M3_CLOSURE_CONTRACT.md',
             'docs/exec-plans/evidence/HG-044/AUTHORITY_CONFIRMATION.md',
             'docs/exec-plans/evidence/HG-044/RAW_DIFF_SCOPE.md',
             'docs/exec-plans/evidence/HG-044/focused-7206b60.json',
             'docs/exec-plans/evidence/HG-044/harness-7206b60.json',
             'docs/exec-plans/evidence/HG-044/unit-7206b60.json',
             'docs/exec-plans/evidence/HG-044/capture-integrity-7206b60.json']
inventory=[]
for path in evidence:
    source=root/path
    assert source.is_file() and not source.is_symlink()
    raw=source.read_bytes()
    inventory.append({'path':path,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)})
(out/'evidence-inventory.json').write_text(json.dumps(inventory,indent=2)+'\n')
record={'task_identity':'harness-governance-v0.1/HG-044',
        'reviewed_head_sha':'027bc2368e36e28aa9956489cb57af297882d671',
        'review_type':'PROTOCOL','status':'PASS','findings':[],
        'evidence_refs':evidence+[prefix+'/evidence-inventory.json'],
        'review_contract_version':'v0.2'}
jsonschema.Draft202012Validator(json.loads((root/'THREAD_REVIEW.schema.json').read_text())).validate(record)
(root/'docs/exec-plans/reviews/HG-044/PROTOCOL.json').write_text(json.dumps(record,indent=2)+'\n')
print('PROTOCOL_REVIEW_PASS 027bc2368e36e28aa9956489cb57af297882d671; no findings')
