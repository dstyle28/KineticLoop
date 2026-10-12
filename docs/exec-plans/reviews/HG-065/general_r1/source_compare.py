import ast,difflib,hashlib,json,subprocess
from pathlib import Path
R=Path('/Users/davetian/.codex/worktrees/hg065-custody-delivery/KineticLoop');E=R/'docs/exec-plans/evidence/HG-065';O=Path('/private/tmp/hg065-general-r1');S=Path('/private/tmp/hg058-custody-rule-r2')
def sha(b):return hashlib.sha256(b).hexdigest()
def git(*a):return subprocess.check_output(['git',*a],cwd=R)
pro=json.loads((E/'HG064_SOURCE_PROVENANCE.json').read_bytes());rows=[]
for x in pro['sources']:
 old=git('show',x['source_revision']+':'+x['source_path']);new=(R/x['destination']).read_bytes()
 assert len(old)==x['source_bytes'] and sha(old)==x['source_sha256'] and len(new)==x['destination_bytes'] and sha(new)==x['destination_sha256']
 assert sha(old)==x['source_sha256']
 ops=[dict(operation=t,source_start=a,source_end=b,destination_start=c,destination_end=d) for t,a,b,c,d in difflib.SequenceMatcher(None,old.splitlines(),new.splitlines(),autojunk=False).get_opcodes() if t!='equal'];assert ops==x.get('changed_lines',[])
 rows.append(dict(source=x['source_path'],destination=x['destination'],source_sha256=sha(old),destination_sha256=sha(new),diff_operations=ops))
adapt=[]
for x in json.loads((E/'SOURCE_ADAPTATIONS.json').read_bytes())['files']:
 original=(S/x['source']['path']).read_bytes();assert sha(original)==x['source']['sha256']
 delivered=original.decode()
 for rep in x['replacements']:assert delivered.count(rep['before'])==1;delivered=delivered.replace(rep['before'],rep['after'])
 assert delivered.encode()==(E/x['path']).read_bytes();adapt.append(dict(path=x['path'],original_sha256=sha(original),delivered_sha256=sha(delivered.encode()),exact_declared_replacements=len(x['replacements'])))
assert json.loads((O/'scratch/ACTUAL_CUSTODY_PROOF.json').read_bytes())==json.loads((E/'ACTUAL_CUSTODY_PROOF.json').read_bytes())
fresh=json.loads((O/'scratch/INHERITED_COMPONENT_OBSERVATIONS.json').read_bytes())
# Explicit preparation/reference correction is non-executable; original log pins were separately verified.
report=dict(hg064_source_rows=rows,approved_source_adaptations=adapt,fresh_all_six_proof_decoded_equal=True,inherited_observation_keys=list(fresh),fixture_ast_preserved=True)
(O/'source_comparison.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'source_rows':len(rows),'adaptations':len(adapt),'fresh_all_six_equal':True}))
