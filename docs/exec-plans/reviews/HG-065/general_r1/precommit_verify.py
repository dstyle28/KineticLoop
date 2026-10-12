import hashlib,json,subprocess
from pathlib import Path
R=Path('/Users/davetian/.codex/worktrees/hg065-custody-delivery/KineticLoop');O=Path('/private/tmp/hg065-general-r1');B='e8e93bd32a83bd2fd6bf89951863d59b37e9d2b3';E='docs/exec-plans/evidence/HG-065/'
def g(*a):return subprocess.check_output(['git',*a],cwd=R)
def sha(b):return hashlib.sha256(b).hexdigest()
receipts=['hg065-precommit-T.json','hg065-precommit-T2.json','hg065-precommit-R.json','hg065-precommit-T3.json','hg065-precommit-R2.json'];commits=g('rev-list','--reverse',B+'..a2f2ff79565375e9bd0cca9013b11e61bf607cac').decode().splitlines();rows=[]
for name,c in zip(receipts,commits,strict=True):
 path=Path('/private/tmp')/name;raw=path.read_bytes();d=json.loads(raw);assert not d['errors']
 assert g('rev-parse',c+'^{tree}').decode().strip()==d['staged_tree']
 paths=g('diff','--name-only',B,c).decode().splitlines();assert sorted(paths)==sorted(x['path'] for x in d['rows'])
 total=0
 for x in d['rows']:
  data=g('show',c+':'+x['path']);assert len(data)==x['bytes'] and sha(data)==x['sha256'];mode=g('ls-tree',c,'--',x['path']).decode().split()[0];assert mode in ('100644','100755')
  if x['path'].startswith(E):assert len(data)<=(8388608 if x['path'].endswith('.gz') else 262144);total+=len(data)
 assert total==d['stored_bytes'] and total<=16777216
 rows.append(dict(commit=c,receipt=name,receipt_sha256=sha(raw),exact_rows=len(d['rows']),stored_bytes=total,tree=d['staged_tree']))
(O/'precommit_verification.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(rows))
