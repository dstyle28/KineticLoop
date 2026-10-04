from pathlib import Path
import json,hashlib,subprocess
root=Path.cwd();out=root/'docs/exec-plans/evidence/KL-080/HG051-feb3236c175df171611fc5b7ddb4f6eeca3ce47c';old=root/'docs/exec-plans/evidence/KL-080/HG049-f85277e27ab5393b7f77b6fea25d4197294d3153';refs={}
for name in ['hosted.collection.json','hosted.execution.json']:
 source=out/(name+'.capture.json');m=json.loads(source.read_text());prior=json.loads((old/(name+'.capture.json')).read_text());assert m['raw_sha256']==prior['raw_sha256'] and m['stored_sha256']==prior['stored_sha256'];assert (root/m['payload']).read_bytes()==(root/prior['payload']).read_bytes()
 assert m['tested_commit']=='feb3236c175df171611fc5b7ddb4f6eeca3ce47c'
 target=old/('HG051-feb3236-'+name+'.capture.json');assert not target.exists()
 m['payload']=prior['payload'];target.write_text(json.dumps(m,indent=2)+'\n');refs[name]={'path':str(target.relative_to(root)),'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'raw_sha256':m['raw_sha256'],'raw_bytes':m['raw_bytes']};source.unlink()
# This duplicate payload was newly captured and uncommitted; exact raw bytes stay
# in the new run's downloaded artifact and the pre-existing immutable Git payload.
new_payload=out/(m['raw_sha256']+'.gz');assert subprocess.run(['git','ls-files','--error-unmatch',str(new_payload)],capture_output=True).returncode!=0;new_payload.unlink()
p=out/'hosted-db-verification.json';j=json.loads(p.read_text());j['raw_artifacts'].update(refs);j['storage_deduplication']='New run-specific envelopes share existing same-directory immutable content-addressed bytes for identical actual collection/execution node lists. Execution provenance remains this new hosted run; no old execution is recertified.';p.write_text(json.dumps(j,indent=2)+'\n')
(out/'dedup.py').write_bytes(Path('/private/tmp/kl080-hg051-dedup.py').read_bytes())
print('DEDUP_NEW_CAPTURE',refs)
