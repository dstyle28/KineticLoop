"""Persist exact-SHA DB review with schema and evidence hash verification."""
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import jsonschema

ROOT = Path.cwd()
RAW = ROOT / 'docs/exec-plans/reviews/HG-044/DB_CONCURRENCY-r6-raw'
audit = json.loads((RAW / 'audit.json').read_text())
supplement = json.loads((RAW / 'supplement.json').read_text())
assert audit['reviewed_sha'] == supplement['reviewed_sha'] == 'cf0b99359d04c136d01fd4c5eeec8a23cd0bbc54'
cases = list(ET.parse(RAW / 'prefix.xml').getroot().iter('testcase'))
assert len(cases) == 2 and all(not list(case) for case in cases)
assert '2 passed' in (RAW / 'prefix.stdout').read_text()
captures = json.loads((RAW / 'selected-captures.json').read_text())
for name, count in [('focused',90),('harness',880),('unit',241)]:
    assert f'{count} passed' in next(c['output'] for c in captures if c['check_id'] == name)
inventory = []
for path in sorted(RAW.rglob('*')):
    if path.is_file() and path.name != 'raw-inventory.json':
        raw = path.read_bytes()
        inventory.append(dict(path=str(path.relative_to(ROOT)), bytes=len(raw),
                              sha256=hashlib.sha256(raw).hexdigest()))
(RAW / 'raw-inventory.json').write_text(json.dumps(inventory,indent=2)+'\n')
review = dict(task_identity='harness-governance-v0.1/HG-044',
              reviewed_head_sha=audit['reviewed_sha'], review_type='DB_CONCURRENCY',
              status='PASS', findings=[], review_contract_version='v0.2',
              evidence_refs=[str(p.relative_to(ROOT)) for p in sorted(RAW.rglob('*')) if p.is_file()] +
              ['docs/exec-plans/governance/HG-044.yaml',
               'docs/exec-plans/evidence/HG-044/GATE_PREFIX_REPAIR.md',
               'docs/exec-plans/evidence/HG-044/GATE_DIAGNOSTIC_06dab6d.md',
               'docs/exec-plans/evidence/HG-044/gate-diagnostic-06dab6d.json',
               'docs/exec-plans/evidence/HG-044/hg044-final-gate-traceback.log',
               'docs/exec-plans/evidence/HG-044/RAW_DIFF_SCOPE.md'])
jsonschema.Draft202012Validator(json.loads((ROOT/'THREAD_REVIEW.schema.json').read_text())).validate(review)
(RAW.parent / 'DB_CONCURRENCY.json').write_text(json.dumps(review,indent=2)+'\n')
print('DB_CONCURRENCY exact-SHA schema-valid PASS persisted')
