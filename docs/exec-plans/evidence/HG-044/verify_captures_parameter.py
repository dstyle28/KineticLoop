"""Verify retained final raw output bytes, launch binding and executed check counts."""
import hashlib
import json
import subprocess
from pathlib import Path

root=Path.cwd();tested=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
here=root/'docs/exec-plans/evidence/HG-044';rows=[]
for key in ('focused','harness','unit','lint','typecheck','validation','source_diff'):
 p=here/f'{key}-{tested[:7]}.json';d=json.loads(p.read_text());raw=d['raw_utf8'].encode()
 assert d['check_id']==key and d['tested_commit']==tested
 assert d['base_commit']=='2c44f456a0daf8e6933f20fc3eadc7e1869d6fff'
 assert d['result']=='PASS' and type(d['exit_code']) is int and d['exit_code']==0
 assert d['raw_sha256']==hashlib.sha256(raw).hexdigest() and d['raw_byte_count']==len(raw)
 rows.append(dict(check_id=key,path=str(p.relative_to(root)),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),raw_sha256=d['raw_sha256'],raw_byte_count=len(raw)))
p=here/f'capture-integrity-{tested[:7]}.json';assert not p.exists()
p.write_text(json.dumps(dict(tested_commit=tested,status='PASS',records=rows),indent=2)+'\n')
print('CAPTURE_INTEGRITY_PASS',tested,len(rows))
