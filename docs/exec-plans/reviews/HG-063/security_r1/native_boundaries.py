import ast,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path('/Users/davetian/.codex/worktrees/hg063-plain-archival-definitions/KineticLoop');sys.path.insert(0,str(ROOT))
from tools.harness import compact_evidence as compact,validate_harness as validator
B='161744c5760561349bdeb17d628e38220640c95b';R='f22a78a622caa1e461099e690583b40f5cf5b925';T='3e8b99a49d9a3f4e7dbb77cd6a66ebf3cbbd1afa'
def git(*a):return subprocess.check_output(['git',*a],cwd=ROOT)
def get(p,r=R):return git('show',r+':'+p)
index=json.loads(get('docs/exec-plans/evidence/HG-063/checks-3e8b99a49d9a/CHECK_INDEX.json'));n=0
for check in index['checks']:
 for a in check['artifacts']:
  raw=compact.read(ROOT,a['evidence_ref'],R,tested=T,command=a['command'],exit_code=0)
  assert hashlib.sha256(raw).hexdigest()==a['raw_identity']['sha256'];n+=1
failed=validator.governance_suffix_errors(ROOT,'b71d2d63f8bc27ab0e905b0be8a0cea5f0122a91','39a9a562cb4b9604916099b1a2af48e270c5b8d7','HG-047','review')
assert failed and any('evidence-envelope-json' in e for e in failed)
tree=ast.parse(get('tools/harness/local_gate.py'))
assets=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='ASSETS' for t in n.targets))
for p in assets:
 if p!='validate_harness.py':assert get('tools/harness/'+p)==get('tools/harness/'+p,B)
audit=compact.audit(ROOT,B,R,'HG-063')
report={'native_decoded_envelopes':n,'original_HG047_strict_RRO_errors':failed,'controller_assets_unchanged_except_scope_validator':list(assets),'compact_audit':audit}
Path('/private/tmp/hg063-security-r1/native_boundaries.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
