"""Refresh exact authorized definition/packet hashes after bounded refinement."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
root=Path.cwd(); here=root/'docs/exec-plans/evidence/HG-040'
bpath=root/'KineticLoop_Harness_Backlog_v0.2.json'; b=json.loads(bpath.read_text())
new=json.loads((here/'KL-078.definition.draft.json').read_text()); b['tasks']=[new if t['id']=='KL-078' else t for t in b['tasks']]
b['task_count']=len(b['tasks']); b['active_task_count']=sum(t['status']!='SUPERSEDED' for t in b['tasks'])
bpath.write_text(json.dumps(b,ensure_ascii=False,indent=2)+'\n')
(root/'docs/exec-plans/active/KL-078.md').write_text((here/'KL-078.packet.draft.md').read_text())
vpath=root/'tools/harness/validate_harness.py'; text=vpath.read_text()
for constant in ['M3_NEXT_WAVE_DEFINITION_HASHES','M3_NEXT_WAVE_PACKET_HASHES']:
 node=next(n for n in ast.parse(text).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==constant for t in n.targets)); values=ast.literal_eval(node.value)
 for name in ['KL-076','KL-078']:
  if 'DEFINITION' in constant:raw=json.dumps(next(t for t in b['tasks'] if t['id']==name),ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
  else:raw=(root/f'docs/exec-plans/active/{name}.md').read_bytes()
  values[name]=hashlib.sha256(raw).hexdigest()
 lines=text.splitlines(keepends=True);lines[node.lineno-1:node.end_lineno]=[constant+' = '+repr(values)+'\n'];text=''.join(lines)
vpath.write_text(text)
spec=importlib.util.spec_from_file_location('repin_v',vpath);v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
p=root/'KineticLoop_Harness_Traceability_v0.3.json';d=json.loads(p.read_text());ts={t['id']:t for t in b['tasks']}; d['tasks']=[v.traceability_projection(ts[t['id']]) if t['id'] in {'KL-076','KL-078'} else t for t in d['tasks']];p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
