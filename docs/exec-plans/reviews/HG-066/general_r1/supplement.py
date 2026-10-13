import json,gzip,lzma,hashlib,subprocess,sys,ast,xml.etree.ElementTree as ET
from pathlib import Path
from collections import Counter
R=Path('/Users/davetian/.codex/worktrees/hg066-multi-owner-contract/KineticLoop');D=R/'docs/exec-plans/evidence/HG-066';C=D/'checks-6287e5c7569a';O=Path('/private/tmp/hg066-general-r1');T='6287e5c7569a5e7553528b28afa5e7ac183b3650';H='fbf0b77fa37b51d95e3c2b432e75ecb35f02830a'
sha=lambda x:hashlib.sha256(x).hexdigest()
def read(path):
 x=json.loads(path.read_bytes())
 if 'kineticloop_evidence' not in x:return path.read_bytes()
 assert x['tested_commit']==T and x['exit_code']==0
 return {'gzip-v1':gzip.decompress,'xz-v1':lzma.decompress}[x['kineticloop_evidence']]((R/x['payload']).read_bytes())
index=json.loads((C/'CHECK_INDEX.json').read_bytes())
for row in index['capture_manifest']:
 b=read(R/row['evidence_ref']);assert len(b)==row['bytes'] and sha(b)==row['sha256']
rece=json.loads(read(C/'definitions-FULL_RECEIPT-json.json'));observers=[]
for row in rece['commands']:
 for stream in ['stdout','stderr']:
  b=read(C/('definitions-'+row['label'].replace('.','-')+'-'+stream+'.json'))
  assert len(b)==row[stream+'_bytes'] and sha(b)==row[stream+'_sha256']
 if row['label'].endswith('.py'):observers.append(row['label'])
assert len(observers)==5
attempts=[]
for prefix in ['26c28bac0d69','b80309acf4ff']:
 p=Path('/private/tmp/hg066-author-'+prefix);raw=(p/'COMMANDS.json').read_bytes();cmds=json.loads(raw)
 attempts.append({'T_prefix':prefix,'commands_sha256':sha(raw),'observed_checks':[{'id':x['check_id'],'exit':x['exit_code']} for x in cmds]})
assert attempts[0]['commands_sha256']=='b13f70a9ce1c8af55fbda2e5516edfbdcf38e31863898ef31dd54bca59588cce'
assert attempts[1]['commands_sha256']=='f3e9bf8f593f517141787390b07344229e9b011b2300d1f5e16368a847d55ac7'
from _pytest.junitxml import mangle_test_address
p=Path('/private/tmp/hg066-author-b80309acf4ff/harness-run');x=json.loads((p/'execution.json').read_bytes());ids=list(x['collections'].values())[0]
tree=ET.parse(p/'junit.xml');pairs=Counter((r.get('classname'),r.get('name')) for r in tree.iter('testcase'))
assert len(ids)==1791 and pairs==Counter(('.'.join(mangle_test_address(n)[:-1]),mangle_test_address(n)[-1]) for n in ids)
naive=Counter((n.split('::')[0][:-3].replace('/','.')+('.'+'.'.join(n.split('::')[1:-1]) if len(n.split('::'))>2 else ''),n.split('::')[-1]) for n in ids)
oldhelper=subprocess.check_output(['git','show','b80309acf4ffca8108d80a1dbc17ba1fbc5c2f16:docs/exec-plans/evidence/HG-066/run_author.py'],cwd=R)
newhelper=(D/'run_author.py').read_bytes();assert oldhelper!=newhelper and b'mangle_test_address' in newhelper
assert not subprocess.check_output(['git','ls-tree','3965cac382d333bd97f6c67fec8ecbe805b5932f','--','docs/exec-plans/governance/HG-066.yaml'],cwd=R)
source=(R/'tools/harness/validate_harness.py').read_text();tree=ast.parse(source)
parents={c:n for n in ast.walk(tree) for c in ast.iter_child_nodes(n)}
calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='hg058_selected_check_errors'];assert len(calls)==1
p=calls[0];guards=[]
while p in parents:
 p=parents[p]
 if isinstance(p,ast.If):guards.append(ast.unparse(p.test))
assert any("change_id == 'HG-058'" in g and 'governance_base' in g and 'HG-066.yaml' in g for g in guards)
import yaml,jsonschema
jsonschema.validate(yaml.safe_load((R/'docs/exec-plans/governance/HG-066.yaml').read_bytes()),json.loads((R/'HARNESS_CHANGE.schema.json').read_bytes()))
summary={'capture_refs_verified':len(index['capture_manifest']),'definition_command_stream_pairs':len(rece['commands']),'bounded_observers':observers,'prior_attempts':attempts,'b803_canonical_JUnit_pairs':len(ids),'b803_naive_pair_symmetric_count':sum((naive-pairs).values())+sum((pairs-naive).values()),'old_helper_corrected_before_T':True,'original_Q_has_no_HG066_guard_trigger':True,'selected_call_guard_chain':guards,'task_schema_valid':True,'no_cross_T_acceptance':True,'review_probe_attempt1':{'exit':1,'reason':'Probe treated complete exact-diagnostic nonzero143 as necessarily interrupted; normative contract permits an observed complete nonzero with exact oracle. Revised independent probe marks interrupted=True and complete=False; rejected. No product/source edit.'}}
(O/'supplement.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary))
