import hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path('/Users/davetian/.codex/worktrees/hg067-host-resource-contract/KineticLoop');OUT=Path('/private/tmp/hg067-security-r1');E=ROOT/'docs/exec-plans/evidence/HG-067'
B='276bcaebbf3b64b4ea128b175a0463b2f650ac7c';T='c3ac6d57c4183ce0c9eb0a7806ebc30673ca58a2';R='ddffdbf75d6ff7b774fa84b00c20e57fc3a24fa5'
sys.path[:0]=[str(E),str(ROOT)]
from tools.harness import compact_evidence as n
from verify_definitions import static
static(B,T)
def git(*a):return subprocess.check_output(['git',*a],cwd=ROOT)
observations=[]
for rev in git('rev-list','--reverse',B+'..'+R).decode().splitlines():
 paths=git('diff','--name-only',B,rev,'--','docs/exec-plans/evidence/HG-067').decode().splitlines();payloads=set();bulk={};total=0
 for p in paths:
  data=n.blob(ROOT,p,rev,n.STORED_LIMIT if p.endswith('.gz') else n.PLAIN_LIMIT);total+=len(data)
  meta=n.envelope(data);assert n.reencoding_record(data) is None
  if p.endswith('.gz'):assert meta is None;continue
  raw=n.read(ROOT,p,rev)
  if meta:payloads.add(meta['payload'])
  else:
   try:value=json.loads(raw,object_pairs_hook=n.unique)
   except (ValueError,UnicodeError):value=None
   assert not n.embedded_raw(value)
  assert not raw.lstrip().startswith(b'diff --git ')
  if len(raw)>=16384:
   sha=n.digest(raw);identifier=meta['payload'] if meta else p
   assert sha not in bulk or bulk[sha]==identifier;bulk[sha]=identifier
 assert all(p in payloads for p in paths if p.endswith('.gz')) and total<=n.TOTAL_LIMIT
 observations.append({'revision':rev,'files':len(paths),'stored_bytes':total,'compact_payloads':len(payloads),'errors':[]})
summary={'reviewed_head_sha':R,'purpose':'Task-local compact storage/classification history only; no HG058 project-native inventory audit','native_source_sha256':n.digest((ROOT/'tools/harness/compact_evidence.py').read_bytes()),'source_AST_inventory_native_limits_clock_arithmetic':'PASS','history':observations}
(OUT/'STORAGE_AND_ADAPTATION.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
