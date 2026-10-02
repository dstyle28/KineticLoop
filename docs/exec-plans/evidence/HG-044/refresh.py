"""Refresh only existing derived hashes and the HG044 contract authority addition."""
import hashlib
import json
from pathlib import Path

root=Path.cwd(); contract='docs/harness/M3_CLOSURE_CONTRACT.md'
def refresh(entries):
 for e in entries:
  path=root/e['path']; e['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
  if 'bytes' in e: e['bytes']=path.stat().st_size
p=root/'CURRENT_DOCUMENT_INDEX.json';d=json.loads(p.read_text())
if contract not in {e['path'] for e in d['documents']}:
 d['documents'].append(dict(document_id='DOC-M3-CLOSURE-V0.1',path=contract,sha256='',status='CURRENT'))
refresh(d['documents']);refresh(d['machine_readable']);p.write_text(json.dumps(d,indent=2)+'\n')
p=root/'HARNESS_DOCUMENT_MANIFEST.json';d=json.loads(p.read_text())
if contract not in {e['path'] for e in d['files']}:
 d['files'].append(dict(path=contract,bytes=0,sha256=''))
refresh(d['files']);p.write_text(json.dumps(d,indent=2)+'\n')
