"""HG037 revision-bound append-only identity, immutable state and provenance audit."""
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

import yaml

ROOT = Path.cwd()
HERE = ROOT/'docs/exec-plans/evidence/HG-037'
BASE = (HERE/'protected-base.txt').read_text().strip()
HEAD = subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
def git(*args):
    return subprocess.check_output(['git',*args])
print('base_commit='+BASE+'\ntested_commit='+HEAD)
for path in ['src','tests/db','tests/unit','migrations','.github','compose.yaml','FROZEN_BASELINE.json',
 '05_KineticLoop_Protocol_v1.2_FROZEN.md','04_KineticLoop_DB_Schema_Design_v0.2_FROZEN.md',
 'CURRENT_REQUIREMENT_SET.json','KineticLoop_Acceptance_Spec_v1.2.2.json','KineticLoop_Integration_Acceptance_v0.1.json',
 'KineticLoop_Evidence_Manifest_v0.1.json','docs/exec-plans/completed','docs/exec-plans/integrations',
 'docs/exec-plans/milestones','docs/exec-plans/reviews','docs/contracts']:
    assert git('diff','--name-only',BASE,HEAD,'--',path)==b'', path
for path in git('diff','--name-only',BASE,HEAD,'--','docs/exec-plans/evidence').decode().splitlines():
    assert path.startswith('docs/exec-plans/evidence/HG-037/'), path
print('PASS all product/Compose/tests/migrations/CI/frozen/requirements/completed/results/evidence/integrations unchanged')
for p in ['KineticLoop_Harness_Backlog_v0.2.json','KineticLoop_Harness_Traceability_v0.3.json']:
 old=json.loads(git('show',BASE+':'+p)); new=json.loads((ROOT/p).read_text())
 assert new['tasks'][:-1]==old['tasks'], p
 assert new['tasks'][-1]['id']=='KL-074'
 assert {k:v for k,v in old.items() if k not in ['tasks','task_count','active_task_count']}=={k:v for k,v in new.items() if k not in ['tasks','task_count','active_task_count']}
 assert not any(t['id']=='KL-074' for t in old['tasks'])
print('PASS exactly one unused namespaced task appended; all completed definitions preserved')
spec=importlib.util.spec_from_file_location('hg037_validator',ROOT/'tools/harness/validate_harness.py')
v=importlib.util.module_from_spec(spec); spec.loader.exec_module(v)
b=json.loads((ROOT/v.BACKLOG).read_text()); t=b['tasks'][-1]
assert t['status']=='NOT_STARTED' and t['requirements_covered']==[] and t['evidence_refs']==[]
assert v.readiness_definition_errors(t)==[]
assert v.packet_errors(t,(ROOT/'docs/exec-plans/active/KL-074.md').read_text())==[]
assert v.traceability_projection(t)==json.loads((ROOT/v.TRACEABILITY).read_text())['tasks'][-1]
assert len(t['check_contracts'])==9
for path in v.result_paths('KL-074')+['docs/exec-plans/integrations/KL-074.json','docs/exec-plans/reviews/KL-074','docs/exec-plans/evidence/KL-074']:
 assert not (ROOT/path).exists(), path
for tid in t['depends_on']:
 paths=v.result_paths_at_revision(ROOT,tid,BASE); assert len(paths)==1
 r=yaml.safe_load(git('show',BASE+':'+paths[0])); assert r['task_status']==r['task_checks_status']=='PASS'
 reviews=[]
 tasks={t['id']:t for t in b['tasks']}
 for typ in tasks[tid]['review_requirements']:
  rv=json.loads(git('show',BASE+f':docs/exec-plans/reviews/{tid}/{typ}.json'))
  assert rv['status']=='PASS' and rv['task_identity']==tasks[tid]['task_identity']
  reviews.append(rv['reviewed_head_sha'])
 assert len(set(reviews))==1
 subprocess.run(['git','merge-base','--is-ancestor',reviews[0],BASE],check=True)
 assert git('show',reviews[0]+':'+paths[0])==git('show',BASE+':'+paths[0])
 print('MERGED_PREREQUISITE',tid,'tested='+r['tested_commit'],'reviewed='+reviews[0])
prov=json.loads((HERE/'preparation-provenance.json').read_text())
for path,metadata in prov['sources'].items():
 raw=(HERE/path).read_bytes(); assert metadata['sha256']==hashlib.sha256(raw).hexdigest() and metadata['bytes']==len(raw)
for path in HERE.glob('run*.log.json'):
 envelope=json.loads(path.read_text()); raw=envelope['content'].encode()
 assert envelope['raw_sha256']==hashlib.sha256(raw).hexdigest() and envelope['raw_bytes']==len(raw)
meta=[json.loads((HERE/f'run36807167973-attempt{i}.json').read_text()) for i in [1,2,3]]
assert len({m['head_sha'] for m in meta})==1
assert [m['conclusion'] for m in meta]==['failure','failure','success']
for name,needle in [('attempt1-failed','234 passed, 10 errors'),('attempt2-failed','243 passed, 1 error'),('attempt3','244 passed')]:
 assert needle in json.loads((HERE/f'run36807167973-{name}.log.json').read_text())['content']
print('PASS same-SHA failure234/10 failure243/1 success244, retrieved reference hashes; actual image causal proof NOT_VERIFIED')
print('PASS governance only; nine prospective KL074 checks NOT_RUN; no product/release claims')
print('HG037_AUDIT_PASS')
