from pathlib import Path
import json,subprocess,hashlib,sys,yaml
r=Path.cwd();before='5812ff2ca2c45bfe88c743e36656ea1921112ed6';tested='feb3236c175df171611fc5b7ddb4f6eeca3ce47c'
assert subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()==before
assert not subprocess.check_output(['git','status','--porcelain']).strip()
sys.path.insert(0,str(r/'tools/harness'));import compact_evidence as c
old=r/'docs/exec-plans/evidence/KL-080'/('HG051-'+tested)/'hosted-db-verification.json';original=old.read_bytes();doc=json.loads(original)
changes=[]
for key in ['collection.json','execution.json']:
 stale=doc['raw_artifacts'][key];correct=doc['raw_artifacts'].pop('hosted.'+key)
 assert not (r/stale['path']).exists()
 doc['raw_artifacts'][key]=correct;changes.append({'artifact':key,'invalid_previous_reference':stale,'correct_reference':correct})
assert len(doc['raw_artifacts'])==len({x['path'] for x in doc['raw_artifacts'].values()})
raws={}
for name,ref in doc['raw_artifacts'].items():
 data=c.blob(r,ref['path'],before,c.PLAIN_LIMIT);assert hashlib.sha256(data).hexdigest()==ref['sha256']
 raw=c.read(r,ref['path'],before,tested=tested);assert len(raw)==ref['raw_bytes'] and hashlib.sha256(raw).hexdigest()==ref['raw_sha256'];raws[name]=raw
manifest=json.loads(raws['manifest.json']);assert manifest['tested_commit']==tested and manifest['status']=='PASS'
for a in manifest['artifacts']+[x['stdout'] for x in manifest['checks']]:
 raw=raws[a['path']];assert len(raw)==a['bytes'] and hashlib.sha256(raw).hexdigest()==a['sha256']
assert set(raws)=={p.name for p in Path('/private/tmp/kl080-hg051-hosted-37161315464/db-evidence-'+tested+'-37161315464-1').iterdir()}
out=r/'docs/exec-plans/evidence/KL-080/HG051-hosted-index-correction';out.mkdir(exist_ok=False)
doc['supersedes']={'path':str(old.relative_to(r)),'revision':before,'sha256':hashlib.sha256(original).hexdigest(),'reason':'The earlier derived index retained two unavailable pre-deduplication references and added corrected references under unintended prefixed keys. Original raw execution, manifest hashes, counts and cleanup are unchanged. This new index replaces only that faulty navigation/provenance index; the earlier bytes remain preserved.'}
new=out/'hosted-db-verification.json';new.write_text(json.dumps(doc,indent=2)+'\n')
report={'reviewed_revision_with_finding':before,'tested_commit':tested,'finding':'Two derived hosted index references were stale after lossless payload sharing; no raw execution or payload bytes were missing.','corrections':changes,'original_faulty_index_preserved':True,'verified_raw_artifact_count':len(raws),'every_reference_exact_git_revision_regular_blob':True,'every_outer_and_raw_hash_verified':True,'all_hosted_manifest_artifact_hashes_match':True,'hosted_counts':manifest['junit'],'no_new_test_execution_claimed':True,'new_authoritative_index':str(new.relative_to(r))}
(out/'correction-validation.json').write_text(json.dumps(report,indent=2)+'\n');(out/'correct-index.py').write_bytes(Path('/private/tmp/kl080-hg051-correct-index.py').read_bytes())
resultpath=r/'docs/exec-plans/completed/KL-080_RESULT.yaml';result=yaml.safe_load(resultpath.read_text());result['decisions'].append('Use '+str(new.relative_to(r))+' as the authoritative hosted execution index. Independent General review found two stale references in the earlier derived index; preserve that old record, correct only new metadata and independently verify every corrected reference and hosted manifest artifact against exact Git bytes.')
result['known_limitations'].append('The original HG051 hosted-db-verification.json index at '+before+' contains two stale navigation references and is superseded by '+str(new.relative_to(r))+'. Its bytes remain historical evidence of the corrected review finding; it is not the current hosted verification index. Raw outputs, tested SHA, counts and cleanup are unchanged; this correction is not a new test run.')
result['files_changed']=sorted(set(result['files_changed']+[str(p.relative_to(r)) for p in out.iterdir()]));resultpath.write_text(yaml.safe_dump(result,sort_keys=False,width=100));assert old.read_bytes()==original
print('CORRECTED_NEW_INDEX_ALL_REFS_PASS',len(raws),'RAW_EXECUTION_UNCHANGED')
