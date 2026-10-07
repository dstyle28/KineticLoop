import hashlib,json,subprocess
from pathlib import Path
import yaml
root=Path('/Users/davetian/.codex/worktrees/e520/KineticLoop');B='9700a1b95d05c856897f74f125cfdf6fb3f6e646';T='74c93c06e83cd5087ecd3b4cc11320b88b246616'
def blob(rev,path):
 entry=subprocess.check_output(['git','ls-tree','-l','-z',rev,'--',path],cwd=root).rstrip(b'\0');meta,name=entry.split(b'\t');mode,kind,oid,size=meta.split();assert mode in (b'100644',b'100755') and kind==b'blob' and int(size)<=262144 and name.decode()==path
 raw=subprocess.check_output(['git','cat-file','blob',oid.decode()],cwd=root);assert len(raw)==int(size);return oid.decode(),raw
T=subprocess.check_output(['git','rev-parse',T],cwd=root,text=True).strip();declaration_oid,data=blob(T,'docs/harness/REVIEW_SOURCE_DECLARATIONS.json');decls=json.loads(data)['declarations'];records=[]
expected={
 'HG-045':('ec6738fd758943d71aa2fcba337a9adaf931385e','478a46a418fc759c1843ce24702ccee7aafcddc2',{'GENERAL':'056e99593cd208fab864b08f46329396fddcd646','PROTOCOL':'cb11622a559a108bc5afae808a0474dd375a99f0','DB_CONCURRENCY':'50d2ec145e7eba78333df7888c9860b8cad4c8b9'}),
 'HG-047':('39a9a562cb4b9604916099b1a2af48e270c5b8d7','b71d2d63f8bc27ab0e905b0be8a0cea5f0122a91',{'GENERAL':'4f8309781e1f62969a9e177e0b181e3fc9dd6579','SECURITY_DATA_BOUNDARY':'c34f8654bdeb2b3d4f4437c28acf81f662089edb'})}
assert len(decls)==6
for d in decls:
 owner=d['owner'].split('/')[1];commit,reviewed,types=expected[owner]
 assert (d['original_review_record_commit'],d['reviewed_head_sha'],d['original_review_record_blob'])==(commit,reviewed,types[d['review_type']])
 owner=d['owner'].split('/')[1];path=f'docs/exec-plans/governance/{owner}.yaml';oid,raw=blob(B,path);record=yaml.safe_load(raw);outputs={c['evidence_ref'] for c in record['checks_run']};assert d['reference'] not in outputs
 original_oid,original=blob(d['original_review_record_commit'],d['review_record_path']);assert original_oid==d['original_review_record_blob'];review=json.loads(original);assert d['reference'] in review['evidence_refs']
 records.append({'owner':d['owner'],'type':d['review_type'],'reference':d['reference'],'original_review_blob':original_oid,'governance_record':path,'governance_blob':oid,'governance_sha256':hashlib.sha256(raw).hexdigest(),'command_output_reference_count':len(outputs),'same_reference_is_command_output':False,'approved_original_tuple_match':True,'purpose_authority':'explicit approved governance declaration; no filename/content/decoder inference','disposition':'source citation identity only; no execution or storage verdict'})
print(json.dumps({'tested_commit':T,'protected_base':B,'declaration_blob':declaration_oid,'source_uses':records,'status':'PASS_DEFINITION_PURPOSE_BOUNDARY_ONLY'},indent=2))
