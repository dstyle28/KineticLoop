"""Write the own governance result only after the selected evidence round passes."""
import json
import subprocess
from pathlib import Path

import yaml

root=Path.cwd();base='fa729ca4bcca0f2c2e7a2aa0601890d1356b8842'
tested=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
here=root/'docs/exec-plans/evidence/HG-044';checks=[]
for key in ('focused','scope','harness','unit','lint','typecheck','validation','diff'):
 p=here/f'{key}-{tested[:7]}.json';data=json.loads(p.read_text())
 assert data.get('result',data.get('status'))=='PASS' and data['tested_commit']==tested,p
 checks.append(dict(check_id=key,command=data.get('command','/private/tmp/hg044-venv/bin/python docs/exec-plans/evidence/HG-044/audit.py'),result='PASS',evidence_ref=str(p.relative_to(root))))
changed=set(subprocess.check_output(['git','diff','--name-only',base,'HEAD'],text=True).splitlines())
changed.update(subprocess.check_output(['git','ls-files','--others','--exclude-standard'],text=True).splitlines())
record_path='docs/exec-plans/governance/HG-044.yaml';changed.add(record_path)
record=dict(change_identity='harness-governance-v0.1/HG-044',display_change_id='HG-044',base_commit=base,tested_commit=tested,change_status='PASS',summary='Ratify minimal isolated TEST M3 exit mapping and mechanically validate exact integrations/prerequisites, dependency ancestry, integrated named task checks and raw provenance, one fresh integrated regression and truthful complete deferred layer ledgers. Preserve M1/M2, HG043 and frozen semantics; create no actual closure instance.',packets_refined=[],files_changed=sorted(changed),checks_run=checks,frozen_impact='NONE',authority_entries_added=['docs/harness/M3_CLOSURE_CONTRACT.md'],known_limitations=[
 'Governance support only. No actual M3 closure, task integration or status update, product/release PASS, production activation or executable shadow is created. KL028/KL029 absence rejects premature closure.',
 'All31 B/10 I dispositions remain required. Twelve deferred B layers include B04 full TEST reauthorization despite mandatory guard support, eight actual API/workflow/DB/eligibility/rendering E2E, B11/B12 pure evaluator PU, B14 worker/fault WF; I04WF, shadow usability and R04E2E remain NOT_RUN.',
 'Historical model evidence remains unverified and unreproduced. Internal service reach/layers, PU equality and historical evaluation fixture provenance cannot be promoted or relabelled.',
 'Synthetic isolated Git fixture data is validator input only, never actual project completion evidence. Existing canonical M1/M2/integration/provenance validator functions are byte-identical.',
 'Prior development rounds are retained as historical input, superseded by strengthened content-oracle and complete-dependency fixture negative tests; only the selected final tested SHA evidence is PASS authority for this governance. The initial uncommitted42PASS focused run is not selected final evidence.',
 'No local PostgreSQL lifecycle or foreign task namespace is run. Unchanged applicable hosted isolated PostgreSQL lifecycle/regression CI must pass at final reviewed PR head.',
 'Fresh independent GENERAL/PROTOCOL/DB_CONCURRENCY/SECURITY_DATA_BOUNDARY reviews bind committed governance/evidence SHA. Only own review-record suffix follows. Stop before actual merge for coordinator serialization; dirty KL055 and peer resources remain untouched.',
])
(root/record_path).write_text(yaml.safe_dump(record,sort_keys=False,width=100))
print(record_path,len(changed))
