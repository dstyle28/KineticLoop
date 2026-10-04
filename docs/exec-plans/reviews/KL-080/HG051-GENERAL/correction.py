from pathlib import Path
import sys,subprocess,json,hashlib
R=Path.cwd();sys.path.insert(0,str(R/'tools/harness'));import compact_evidence as ce
H='417b65ee68244dc86ab02add231b24dc662be790';OLD='5812ff2ca2c45bfe88c743e36656ea1921112ed6';T='feb3236c175df171611fc5b7ddb4f6eeca3ce47c'
P='docs/exec-plans/evidence/KL-080/HG051-hosted-index-correction/hosted-db-verification.json'
def git(*a):return subprocess.check_output(['git',*a])
def blob(p,r=H):return git('show',r+':'+p)
def sha(b):return hashlib.sha256(b).hexdigest()
n=json.loads(blob(P));prior=n['supersedes'];assert prior['revision']==OLD and sha(blob(prior['path'],OLD))==prior['sha256'] and blob(prior['path'])==blob(prior['path'],OLD)
refs=n['raw_artifacts'];assert len(refs)==15 and not any(k.startswith('hosted.') for k in refs)
raw={}
for name,r in refs.items():
 assert sha(blob(r['path']))==r['sha256'];b=ce.read(R,r['path'],H,tested=T,exit_code=0);assert len(b)==r['raw_bytes'] and sha(b)==r['raw_sha256'];raw[name]=b
manifest=json.loads(raw['manifest.json']);assert manifest['tested_commit']==T and manifest['status']=='PASS' and manifest['provenance']['github_run_id']=='37161315464';assert not manifest['remaining_containers'] and not manifest['remaining_volumes']
for r in manifest['artifacts']+[x['stdout'] for x in manifest['checks']]:
 assert len(raw[r['path']])==r['bytes'] and sha(raw[r['path']])==r['sha256']
assert all(x['exit_code']==0 and not x['interrupted'] for x in manifest['checks'])
delta=git('diff','--name-status',OLD,H).decode().splitlines();assert len(delta)==4
for line in delta:
 mode,p=line.split('\t');assert (mode=='M' and p=='docs/exec-plans/completed/KL-080_RESULT.yaml') or (mode=='A' and p.startswith('docs/exec-plans/evidence/KL-080/HG051-hosted-index-correction/'))
assert not git('diff',OLD,H,'--','src','tests','docs/contracts','CURRENT_REQUIREMENT_SET.json','FROZEN_BASELINE.json')
result=blob('docs/exec-plans/completed/KL-080_RESULT.yaml').decode();assert 'Use '+P+' as the' in result and 'two stale navigation references and is superseded by '+P in result
out={'reviewed_head_sha':H,'previous_reviewed_head_sha':OLD,'tested_commit':T,'authoritative_index':P,'verified_artifact_keys':sorted(refs),'verified_hosted_manifest_hashes':True,'superseded_record_byte_identical':True,'source_tests_contracts_unchanged':True,'delta':delta,'finding':'KL080-HG051-GENERAL-001','finding_status':'CLOSED','status':'PASS'}
Path(__file__).with_name('correction.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
