"""Refresh hashes of actually changed indexed/manifest paths and append the new packet."""
import hashlib
import json
from pathlib import Path

root=Path.cwd()
def refresh(entries):
    for e in entries:
        p=root/e['path']
        e['sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
        if 'bytes' in e:
            e['bytes']=p.stat().st_size
p=root/'CURRENT_DOCUMENT_INDEX.json'
d=json.loads(p.read_text()); refresh(d['documents']); refresh(d['machine_readable']); p.write_text(json.dumps(d,indent=2)+'\n')
p=root/'HARNESS_DOCUMENT_MANIFEST.json'
d=json.loads(p.read_text()); refresh(d['files'])
new='docs/exec-plans/active/KL-074.md'
if not any(e['path']==new for e in d['files']):
 f=root/new; d['files'].append({'path':new,'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()})
p.write_text(json.dumps(d,indent=2)+'\n')
