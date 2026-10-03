from pathlib import Path
import importlib.util, subprocess, json, os, copy, gzip, hashlib, sys
ROOT=Path('/Users/davetian/.codex/worktrees/83f7/KineticLoop')
WORK=Path('/private/tmp/hg051-r2-security-20261003')
SOURCE='0557dbd8f2196df871af20c0982bdc2526f0ad6e'
BASE='b877db0edd2e4550d6ea81750656112fb7f2e223'
checks=[]
def git(root,*args):
    p=subprocess.run(['git',*args],cwd=root,capture_output=True)
    if p.returncode: raise RuntimeError(p.stderr.decode(errors='replace'))
    return p.stdout

def passed(name, **info):
    checks.append(dict(name=name,status='PASS',**info))
    print(json.dumps(checks[-1]),flush=True)

def reject(name, fn):
    try: fn()
    except (ValueError,OSError,RuntimeError) as ex: passed(name,rejected=str(ex)[:300]); return
    raise AssertionError('ACCEPTED '+name)

installed=WORK/'gate/tools/harness'; installed.mkdir(parents=True,exist_ok=True)
for name in ('validate_harness.py','compact_evidence.py','db_ci_pytest.py','db_ci.py','gate_validate.py','gate_pytest.py'):
    (installed/name).write_bytes(git(ROOT,'show',SOURCE+':tools/harness/'+name))
spec=importlib.util.spec_from_file_location('security_installed_validator',installed/'validate_harness.py')
v=importlib.util.module_from_spec(spec); spec.loader.exec_module(v); ce=v.compact_evidence
exact_schema=git(ROOT,'show',SOURCE+':'+ce.MAPPING_SCHEMA)
assert ce.HISTORICAL_SCHEMA_BYTES==exact_schema
assert not (WORK/'gate'/ce.MAPPING_SCHEMA).exists()
assert (ce.PLAIN_LIMIT,ce.STORED_LIMIT,ce.RAW_LIMIT,ce.TOTAL_LIMIT)==(262144,8388608,67108864,16777216)
passed('installed-exact-pinned-schema-with-no-adjacent-schema',sha256=ce.digest(exact_schema))
canonical=ce.historical_originals()
malicious=ce.historical_schema(); malicious['properties']['entries']['prefixItems'][0]['properties']['original']['const']['raw_sha256']='0'*64
(WORK/'gate'/ce.MAPPING_SCHEMA).write_text(json.dumps(malicious))
candidate=WORK/'candidate'; candidate.mkdir(exist_ok=True)
for name,data in [('tampered',json.dumps(malicious).encode()),('reformatted',json.dumps(ce.historical_schema()).encode()),('oversize',b' '*(ce.PLAIN_LIMIT+1))]:
    (candidate/ce.MAPPING_SCHEMA).write_bytes(data)
    assert v.validate(candidate,None)[0].startswith('historical-schema-authority:')
    assert ce.historical_originals()==canonical
    passed('installed-candidate-schema-'+name+'-rejected')
(candidate/ce.MAPPING_SCHEMA).unlink()
assert v.validate(candidate,None)[0].startswith('historical-schema-authority:')
passed('installed-missing-schema-rejected')
(candidate/ce.MAPPING_SCHEMA).symlink_to(ROOT/ce.MAPPING_SCHEMA)
assert v.validate(candidate,None)[0].startswith('historical-schema-authority:')
passed('installed-symlink-schema-rejected')
(candidate/ce.MAPPING_SCHEMA).unlink(); (candidate/ce.MAPPING_SCHEMA).write_bytes(exact_schema)
assert not v.historical_schema_authority_errors(candidate)
passed('installed-exact-candidate-schema-accepted')
os.chdir(candidate)
assert ce.historical_originals()==canonical
passed('ambient-and-working-directory-schema-cannot-widen-authority')
fixture=WORK/'fixture'; fixture.mkdir(exist_ok=True)
git(fixture,'init','-q'); git(fixture,'config','user.name','HG051 independent security probe'); git(fixture,'config','user.email','probe@example.invalid')
objects=Path(git(ROOT,'rev-parse','--git-path','objects').decode().strip())
if not objects.is_absolute(): objects=(ROOT/objects).resolve()
(fixture/'.git/objects/info/alternates').write_text(str(objects)+'\n')
history='477b213f67429f571b60d5701f02892ab9c1cbbf'
git(fixture,'update-ref','HEAD',history); git(fixture,'read-tree',history)
raws={}
for original in canonical:
    raw=ce.archive_original(ROOT,original); raws[original['path']]=raw
    assert git(ROOT,'rev-parse',original['revision']+':'+original['path']).decode().strip()==original['blob_id']
    assert ce.read(ROOT,original['path'],original['revision'])==raw
    record,payload=ce.archive_envelope(original,raw)
    dest=fixture/original['path']; dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(record,indent=2)+'\n'); (fixture/record['payload']).write_bytes(payload)
    git(fixture,'add','--',original['path'],record['payload'])
    passed('original-blob-and-archival-capture-'+original['blob_id'],raw_bytes=len(raw),raw_sha256=ce.digest(raw),stored_bytes=len(payload),execution=original['execution'])
git(fixture,'commit','-qm','temporary four authorized storage objects')
storage=git(fixture,'rev-parse','HEAD').decode().strip()
mapping=ce.archive_mapping(fixture,storage)
map_path=fixture/ce.MAPPING_PATH; map_path.write_text(json.dumps(mapping,indent=2)+'\n'); git(fixture,'add','--',ce.MAPPING_PATH); git(fixture,'commit','-qm','temporary mapping')
head=git(fixture,'rev-parse','HEAD').decode().strip()
assert ce.validate_archive(fixture,mapping,head,verify_originals=True)==raws
assert not ce.audit(fixture,history,head,'KL-080')['errors']
passed('installed-independent-real-inventory-positive',storage=storage,mapping_commit=head,bytes=sum(map(len,raws.values())))
for original in canonical:
    path=original['path']; assert ce.read_archive(fixture,path,head)==raws[path]
    reject('ordinary-read-rejects-archive-'+original['blob_id'],lambda path=path: ce.read(fixture,path,head))
    assert not v.evidence_exists(fixture,path,head)
    assert not v.review_evidence_exists(fixture,path,head,head,'KL-080',True)
    entry=next(x for x in mapping['entries'] if x['original']['path']==path)
    reject('m3-reader-rejects-archive-'+original['blob_id'],lambda path=path,entry=entry: v.m3_evidence_bytes(fixture,dict(path=path,revision=head,sha256=entry['storage']['envelope_sha256']),head))
passed('installed-result-review-m3-cannot-use-archive')
for field,value in [('exit_code',0),('result','PASS'),('timestamp','invented')]:
    bad=copy.deepcopy(mapping); bad['entries'][1]['original']['execution'][field]=value
    reject('failed-execution-'+field+'-immutable',lambda bad=bad: ce.validate_archive(fixture,bad,head))
for field,value in [('task_status','PASS'),('task_checks_status','PASS'),('integration_status','MERGED'),('review_status','PASS')]:
    bad=copy.deepcopy(mapping); bad['historical_outcome'][field]=value
    reject('historical-'+field+'-immutable',lambda bad=bad: ce.validate_archive(fixture,bad,head))
for field,value in [('payload','../borrow.gz'),('envelope_path','docs/exec-plans/evidence/KL-079/other'),('revision','HEAD'),('payload_bytes',ce.STORED_LIMIT+1),('envelope_bytes',ce.PLAIN_LIMIT+1),('payload_sha256','0'*64)]:
    bad=copy.deepcopy(mapping); bad['entries'][0]['storage'][field]=value
    reject('installed-storage-'+field+'-binding',lambda bad=bad: ce.validate_archive(fixture,bad,head))
for label,fn in [('duplicate',lambda m:m['entries'].append(m['entries'][0])),('missing',lambda m:m['entries'].pop())]:
    bad=copy.deepcopy(mapping); fn(bad); reject('installed-mapping-'+label,lambda bad=bad:ce.validate_archive(fixture,bad,head))
ordinary='docs/exec-plans/evidence/KL-080/probe.log'; target=fixture/ordinary
for encoding in ('utf-8','utf-8-sig','utf-16-le','utf-16-be','utf-32-le','utf-32-be'):
    for label,value in [('direct',mapping),('list',[mapping]),('dict',{'wrapped':mapping}),('markerless',{k:v for k,v in mapping.items() if k!=ce.MARKER})]:
        raw=json.dumps(value).encode(encoding); target.write_bytes(raw)
        reject('reserved-'+encoding+'-'+label,lambda:ce.read(fixture,ordinary,None))
        stored=gzip.compress(raw,mtime=0); payload=str(target.parent.relative_to(fixture)/(ce.digest(raw)+'.gz')); (fixture/payload).write_bytes(stored)
        record={ce.MARKER:ce.FORMAT,'payload':payload,'stored_sha256':ce.digest(stored),'stored_bytes':len(stored),'raw_sha256':ce.digest(raw),'raw_bytes':len(raw),'tested_commit':head,'command':'probe','exit_code':0,'timestamp':None,'test_counts':{}}
        nested='docs/exec-plans/evidence/KL-080/outer.json'; (fixture/nested).write_text(json.dumps(record))
        reject('nested-reserved-'+encoding+'-'+label,lambda:ce.read(fixture,nested,None))
# Bounded classification must still reject damaged markerless archival JSON.
for raw in (json.dumps(mapping).encode()[:-10],json.dumps(mapping).replace('kineticloop_evidence','kineticloop\\u005fevidence').encode()[:-10]):
    target.write_bytes(raw); reject('malformed-reserved-json',lambda:ce.read(fixture,ordinary,None))
plain=b'actual execution stdout: 2 passed in 0.01s\n'; target.write_bytes(plain)
assert ce.read(fixture,ordinary,None)==plain
ce.capture(fixture,'docs/exec-plans/evidence/KL-080/valid.json',plain,head,'probe',0)
assert ce.read(fixture,'docs/exec-plans/evidence/KL-080/valid.json',None,tested=head,command='probe',exit_code=0)==plain
reject('ordinary-exit-binding',lambda:ce.read(fixture,'docs/exec-plans/evidence/KL-080/valid.json',None,exit_code=1))
passed('ordinary-gzip-v1-positive-and-pass-bindings-preserved')
realgit=ce.git
original_commit=canonical[0]['revision']
def unavailable(root,*args):
    if original_commit+'^{commit}' in args: raise ValueError('independent-unavailable-original')
    return realgit(root,*args)
ce.git=unavailable
assert ce.read_archive(fixture,canonical[0]['path'],head)==raws[canonical[0]['path']]
reject('original-verification-no-head-or-archive-fallback',lambda:ce.archive_original(fixture,canonical[0]))
assert ce.archive_audit(fixture,head)[0]
ce.git=realgit
passed('retrieval-without-originals-does-not-certify-original-proof')
# Commit exact deletion using index operations, leaving all source objects intact.
git(fixture,'read-tree',head)
for item in mapping['entries']:
    git(fixture,'update-index','--force-remove','--',item['original']['path'],item['storage']['payload'])
git(fixture,'update-index','--force-remove','--',ce.MAPPING_PATH)
tree=git(fixture,'write-tree').decode().strip(); deleted=git(fixture,'commit-tree',tree,'-p',head,'-m','temporary full archive deletion').decode().strip()
assert ce.audit(fixture,head,deleted,'HG-999')['errors']
assert ce.audit(fixture,history,deleted,'KL-080')['errors']
passed('complete-deletion-cannot-evade-merged-or-first-migration-audit')
# No migration or frozen/runtime/production changes in the reviewed real task.
changed=git(ROOT,'diff','--name-only',BASE,SOURCE).decode().splitlines()
assert not any(p.startswith(('src/','migrations/','tests/db/','docs/exec-plans/evidence/KL-080/','docs/exec-plans/completed/KL-080_RESULT')) for p in changed)
for p in ('05_KineticLoop_Protocol_v1.2_FROZEN.md','04_KineticLoop_DB_Schema_Design_v0.2_FROZEN.md','FROZEN_BASELINE.json','CURRENT_REQUIREMENT_SET.json'):
    assert git(ROOT,'show',BASE+':'+p)==git(ROOT,'show',SOURCE+':'+p)
passed('no-kl080-migration-frozen-runtime-db-production-or-requirement-change')
report=dict(source_sha=SOURCE,base_sha=BASE,status='PASS',checks=checks,installed_decoder_sha256=ce.digest((installed/'compact_evidence.py').read_bytes()),note='Temporary archive bytes are integrity probes only; no execution/PASS inference from archival metadata.')
(WORK/'probes.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS '+str(len(checks))+' independent checks')
