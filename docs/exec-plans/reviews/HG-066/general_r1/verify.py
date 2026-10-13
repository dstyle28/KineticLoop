import os,sys,json,gzip,lzma,hashlib,subprocess,ast,xml.etree.ElementTree as ET
from pathlib import Path
from collections import Counter
R=Path('/Users/davetian/.codex/worktrees/hg066-multi-owner-contract/KineticLoop'); E='docs/exec-plans/evidence/HG-066/'; C=E+'checks-6287e5c7569a/'
B='3768c1b4366677934cb952ef808343edcee4e438';T='6287e5c7569a5e7553528b28afa5e7ac183b3650';H='fbf0b77fa37b51d95e3c2b432e75ecb35f02830a';OUT=Path('/private/tmp/hg066-general-r1')
sha=lambda b:hashlib.sha256(b).hexdigest()
def git(*a):return subprocess.check_output(['git',*a],cwd=R)
def blob(p,r=H):return git('show',r+':'+p)
def j(p,r=H):return json.loads(blob(p,r))
def raw(p):
 b=blob(p);x=json.loads(b)
 if 'kineticloop_evidence' not in x:return b
 assert x['tested_commit']==T and x['exit_code']==0
 packed=blob(x['payload']);assert len(packed)==x['stored_bytes'] and sha(packed)==x['stored_sha256']
 b={'gzip-v1':gzip.decompress,'xz-v1':lzma.decompress}[x['kineticloop_evidence']](packed)
 assert len(b)==x['raw_bytes'] and sha(b)==x['raw_sha256'];return b
def data(p):return json.loads(raw(C+p))
assert git('rev-parse','HEAD').decode().strip()==H and not git('status','--porcelain')
assert sha(blob(E+'PACKET.md'))=='755cdb3a38226067ab7f76d6456dfdbecc166790d67791d32f4c30365b6196ab'
assert sha(blob(C+'CHECK_INDEX.json'))=='7646a93b6ad2d3e30e7c2b4916f52ab82be303802b9ac447af5a3e69f9a1760d'
summary={'B':B,'T':T,'R':H,'tree':git('rev-parse',H+'^{tree}').decode().strip()}
commands=data('COMMANDS.json');author=[x for x in commands if not x['check_id'].endswith('-collection')]
assert len(author)==8 and all(x['exit_code']==0 for x in author)
for x in author:
 p=C+x['check_id']+'.json';assert sha(raw(p))==x['stdout_stderr_sha256']
summary['author_checks']=[{'id':x['check_id'],'observed_exit':x['exit_code'],'argv':x['argv']} for x in author]
from _pytest.junitxml import mangle_test_address
ident={}
for name,count in [('validator',182),('unit',247),('harness',1791)]:
 c=data(name+'-collection-json.json');x=data(name+'-execution-json.json');tree=ET.fromstring(raw(C+name+'-junit-xml.json'))
 ids=list(c['collections'].values())[0];assert len(ids)==count and len(set(ids))==count
 assert c['exit_code']==x['exit_code']==0 and not c['errors'] and not x['errors'] and not c['started'] and not c['reports']
 assert all(v==ids for v in x['collections'].values()) and Counter(ids)==Counter(x['started'])
 for phase in ['setup','call','teardown']:
  reports=[r for r in x['reports'] if r['phase']==phase];assert Counter(ids)==Counter(r['nodeid'] for r in reports) and all(r['outcome']=='passed' for r in reports)
 pairs=[('.'.join(mangle_test_address(n)[:-1]),mangle_test_address(n)[-1]) for n in ids]
 assert Counter(pairs)==Counter((n.get('classname'),n.get('name')) for n in tree.iter('testcase'))
 assert not any(list(tree.iter(k)) for k in ['error','failure','skipped'])
 ident[name]={'cases':count,'phases':count*3,'nodeids_sha256':sha(json.dumps(ids).encode()),'exact_positive_equality':True}
receipt=data('definitions-FULL_RECEIPT-json.json');expected=j(E+'EXPECTED_IDENTITIES.json')
assert len(receipt['commands'])==23 and all(x['exit_code']==0 for x in receipt['commands'])
for s in expected['suites']:
 label=s['file'][:-3];prefix='definitions-'+('preserved-hg065-' if s['file']=='test_custody_definition.py' else '')+label
 c=data(prefix+'-collection-json.json');x=data(prefix+'-execution-json.json');tree=ET.fromstring(raw(C+prefix+'-junit-xml.json'))
 ids=s['identities'];assert c['collections']==x['collections']==x['started']==ids and len(set(ids))==len(ids)
 assert c['exit_code']==x['exit_code']==0 and not c['errors'] and not x['errors'] and not c['started'] and not c['reports']
 for phase in ['setup','call','teardown']:
  reports=[r for r in x['reports'] if r['when']==phase];assert Counter(ids)==Counter(r['nodeid'] for r in reports) and all(r['outcome']=='passed' and r['wasxfail'] is None for r in reports)
 assert Counter((label,n.split('::')[-1]) for n in ids)==Counter((n.get('classname'),n.get('name')) for n in tree.iter('testcase'))
 assert not any(list(tree.iter(k)) for k in ['failure','error','skipped'])
ident['definitions']={'cases':sum(len(s['identities']) for s in expected['suites']),'prospective':677,'preserved_v1':156,'phases':2499,'observers':5,'commands':23}
summary['identities']=ident
sys.path[:0]=[str(R),str(R/E)]
from tools.harness import validate_harness as v
from tools.harness import compact_evidence as n
from verify_delivery import verify
summary['delivery']=verify()
p=j(E+'DELIVERY_PROVENANCE.json');ad={r['path']:r for r in j(E+'SOURCE_ADAPTATIONS.json')['files']}
# Separately reconstruct all original bytes and compare full AST including every Constant.
source=[]
for row in p['reviewed_sources']:
 delivered=blob(E+row['path']);original=delivered
 if row['path'] in ad:
  a=ad[row['path']];lines=delivered.decode().splitlines(keepends=True)
  for d in reversed(a['changes']):lines[d['destination_start']:d['destination_end']]=d['original'].splitlines(keepends=True)
  original=''.join(lines).encode();norm=original.decode()
  for d in a['permitted_path_changes']:norm=norm.replace(d['before'],d['after'])
  assert ast.dump(ast.parse(norm),include_attributes=False)==ast.dump(ast.parse(delivered),include_attributes=False)
 assert sha(original)==row['sha256'] and len(original)==row['bytes'];source.append({'path':row['path'],'original_sha256':sha(original),'delivered_sha256':sha(delivered)})
summary['source_bindings']=source
for group in ['documents','machine_readable']:
 for row in j('CURRENT_DOCUMENT_INDEX.json')[group]:assert sha(blob(row['path']))==row['sha256']
for row in j('HARNESS_DOCUMENT_MANIFEST.json')['files']:
 assert sha(blob(row['path'],T))==row['sha256'] and row['path']!='docs/exec-plans/governance/HG-066.yaml'
assert blob('HARNESS_DOCUMENT_MANIFEST.json',T)==blob('HARNESS_DOCUMENT_MANIFEST.json')
summary['manifest_entries']=len(j('HARNESS_DOCUMENT_MANIFEST.json')['files'])
changed=git('diff','--name-only',B,H).decode().splitlines();assert all(v.matches(x,v.HG066_ALLOWED_PATTERNS) for x in changed)
commits=git('rev-list','--reverse',T+'..'+H).decode().splitlines();edges=[]
for commit in commits:
 parents=git('rev-list','--parents','-n','1',commit).decode().split()[1:];assert len(parents)==1
 diff=git('diff','--name-status',parents[0],commit).decode().splitlines()
 assert all(s.startswith('A\t'+E) or s=='A\tdocs/exec-plans/governance/HG-066.yaml' for s in diff)
 edges.append({'parent':parents[0],'child':commit,'additions':len(diff),'sha256':sha(('\n'.join(diff)+'\n').encode())})
assert not v.governance_suffix_errors(R,T,H,'HG-066','tested');summary['edges']=edges
# Exact precommit tree mapping, compare each recorded own row to committed tree.
pre=[]
for number,commit in [(1,'26c28bac0d69589b0beed7a3a9ad4e06ccbfd11a'),(2,'b80309acf4ffca8108d80a1dbc17ba1fbc5c2f16'),(3,T),(4,H)]:
 report=j(E+f'NATIVE_PRECOMMIT_CANDIDATE_{number}.json') if number<4 else json.loads(Path('/private/tmp/hg066-precommit-result-1.json').read_bytes())
 assert report['staged_tree']==git('rev-parse',commit+'^{tree}').decode().strip() and not report['errors']
 rows=report['files'];paths=[p for p in git('diff','--name-only',B,commit).decode().splitlines() if p.startswith((E,'docs/exec-plans/reviews/HG-066/'))]
 assert set(paths)=={r['path'] for r in rows} and len(paths)==len(rows)
 for row in rows:
  b=blob(row['path'],commit);assert len(b)==row['bytes'] and sha(b)==row['sha256'] and row['classification']=='NATIVE_VALIDATED'
 assert sum(x['bytes'] for x in rows)==report['total_bytes']<=16777216
 pre.append({'commit':commit,'tree':report['staged_tree'],'files':len(rows),'bytes':report['total_bytes']})
summary['precommit']=pre
summary['native_audit']=n.audit(R,B,H,'HG-066');assert not summary['native_audit']['errors']
(OUT/'verification.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({'verified':True,'identities':ident,'precommit':pre,'edges':edges,'native_audit':summary['native_audit']}))
