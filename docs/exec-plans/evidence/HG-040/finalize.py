"""Finalize only after externally recorded and locally verified HG039 normal merge."""
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

root=Path.cwd(); here=root/'docs/exec-plans/evidence/HG-040'
pr=json.loads((here/'HG039-normal-merge.json').read_text()); assert pr['state']=='MERGED'
merge=pr['mergeCommit']['oid']; base=(here/'protected-base.txt').read_text().strip()
assert len(subprocess.check_output(['git','rev-list','--parents','-n','1',merge],text=True).split())==3
subprocess.run(['git','merge-base','--is-ancestor',merge,base],check=True)
assert not list((root/'docs/exec-plans/completed').glob('KL-076_RESULT.*'))
bpath=root/'KineticLoop_Harness_Backlog_v0.2.json'; b=json.loads(bpath.read_text()); ts={t['id']:t for t in b['tasks']}
assert 'KL-078' not in ts
new=json.loads((here/'KL-078.definition.draft.json').read_text()); assert new['status']=='NOT_STARTED' and not new['evidence_refs']
b['tasks'].append(new)
old=ts['KL-076']; assert old['status']=='NOT_STARTED'; assert 'KL-078' not in old['depends_on']
old['depends_on'].append('KL-078')
old['entry_conditions'].append('KL078 exact upstream preparation repair normally merged; owner-generated projection/dependency/READY build and actual T3 feasibility verified without target output seeds.')
old['context_files'].append('docs/exec-plans/completed/KL-078_RESULT.yaml')
bpath.write_text(json.dumps(b,ensure_ascii=False,indent=2)+'\n')
p=root/'docs/exec-plans/active/KL-076.md'; text=p.read_text()
text=text.replace('- KL-074\n\n### Conditional dependencies','- KL-074\n- KL-078\n\n### Conditional dependencies',1)
text=text.replace('## Read first','- '+old['entry_conditions'][-1]+'\n\n## Read first',1)
text=text.replace('- docs/exec-plans/completed/KL-074_RESULT.yaml','- docs/exec-plans/completed/KL-074_RESULT.yaml\n- docs/exec-plans/completed/KL-078_RESULT.yaml',1)
text=text.replace('Missing upstream capability is a separately scoped prerequisite, never a raw output seed workaround.',
 'KL078 is the separately scoped upstream projection/dependency/build capability prerequisite; use its exact merged owner ingress and immutable source references. Missing upstream capability remains a separately scoped prerequisite, never a raw output seed workaround.',1)
p.write_text(text)
(root/'docs/exec-plans/active/KL-078.md').write_text((here/'KL-078.packet.draft.md').read_text())
vpath=root/'tools/harness/validate_harness.py'; text=vpath.read_text()
text=text.replace("'KL-075', 'KL-076', 'KL-077'}", "'KL-075', 'KL-076', 'KL-077', 'KL-078'}")
# Two exact hashes for refined KL076; add new KL078 hashes to both guard maps.
for name,constant in [('KL-076','M3_NEXT_WAVE_DEFINITION_HASHES'),('KL-078','M3_NEXT_WAVE_DEFINITION_HASHES'),('KL-076','M3_NEXT_WAVE_PACKET_HASHES'),('KL-078','M3_NEXT_WAVE_PACKET_HASHES')]:
 import ast
 tree=ast.parse(text); node=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==constant for t in n.targets))
 values=ast.literal_eval(node.value)
 if 'DEFINITION' in constant:
  task=next(t for t in b['tasks'] if t['id']==name); raw=json.dumps(task,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
 else:raw=(root/f'docs/exec-plans/active/{name}.md').read_bytes()
 values[name]=hashlib.sha256(raw).hexdigest()
 lines=text.splitlines(keepends=True); lines[node.lineno-1:node.end_lineno]=[constant+' = '+repr(values)+'\n']; text=''.join(lines)
vpath.write_text(text)
spec=importlib.util.spec_from_file_location('hg040_v',vpath); v=importlib.util.module_from_spec(spec); spec.loader.exec_module(v)
tpath=root/'KineticLoop_Harness_Traceability_v0.3.json'; trace=json.loads(tpath.read_text())
trace['tasks']=[v.traceability_projection(old) if t['id']=='KL-076' else t for t in trace['tasks']]
trace['tasks'].append(v.traceability_projection(new)); tpath.write_text(json.dumps(trace,ensure_ascii=False,indent=2)+'\n')
plan=root/'06_KineticLoop_Project_Plan_v0.6_HARNESS_HARDENED.md'
plan.write_text(plan.read_text()+'''\n\n## Upstream preparation prerequisite — HG040\n\nKL078 repairs exactly existing RecordProjection/BuildManifest capabilities for\nserver-owned immutable S21 revision and actual same-subject SEALED factset inputs\nwith independent short preparation transactions and local S23 completion locks.\nIt proves actual owner-built canonical factset → projection/dependency → READY\nbuild → T3 publication, with immutable/replay/duplicate/rollback/no-authority\ndenials. KL076 waits for its normal merge and retains only S34–S37 F/D/N scope.\nKL078 starts NOT_STARTED, serializes transaction_interfaces and declares every\nhelper/module explicitly. Frozen/wire/registry/coordination boundaries and all\nproduct/layer/release states remain unchanged. No downstream execution is added.\n''')
mpath=root/'HARNESS_DOCUMENT_MANIFEST.json'; m=json.loads(mpath.read_text()); path='docs/exec-plans/active/KL-078.md'
assert not any(e['path']==path for e in m['files']); m['files'].append({'path':path,'bytes':0,'sha256':'0'*64})
m['files'].sort(key=lambda e:e['path']); mpath.write_text(json.dumps(m,indent=2)+'\n')
print('HG040_EXACT_UPSTREAM_DEFINITION_FINALIZED',base)
