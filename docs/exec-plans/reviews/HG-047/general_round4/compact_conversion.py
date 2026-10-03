from pathlib import Path
import hashlib, importlib.util, json, subprocess, xml.etree.ElementTree as ET
R=Path('/Users/davetian/.codex/worktrees/ffff/KineticLoop')
H='b71d2d63f8bc27ab0e905b0be8a0cea5f0122a91'
D=R/'docs/exec-plans/reviews/HG-047/general_round4'
T=Path('/private/tmp/hg047-general-r4')
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip()==H
spec=importlib.util.spec_from_file_location('compact',R/'tools/harness/compact_evidence.py');ce=importlib.util.module_from_spec(spec);spec.loader.exec_module(ce)
checks=json.loads((D/'checks.json').read_text());check=next(c for c in checks['checks'] if c['check']=='targeted')
assert check['status']=='FAIL' and check['exit_code']==1
stamp=next(ET.parse(T/'targeted.xml').iter('testsuite')).get('timestamp')
converted=[];mapping={}
for old,new,key in [('targeted.log','targeted-log.json','log'),('targeted.xml','targeted-xml.json','junit')]:
 raw=(T/old).read_bytes();assert (D/old).read_bytes()==raw
 ref=str((D/new).relative_to(R));manifest=ce.capture(R,ref,raw,H,check['command'],1,stamp)
 assert ce.read(R,ref,None,tested=H,command=check['command'],exit_code=1)==raw
 assert manifest['raw_sha256']==check[key+'_sha256'] and manifest['raw_bytes']==len(raw)
 mapping[str((D/old).relative_to(R))]=ref
 check[key]=ref;check[key+'_raw_sha256']=check.pop(key+'_sha256');check[key+'_envelope_sha256']=hashlib.sha256((D/new).read_bytes()).hexdigest()
 converted.append({'old_uncommitted_path':str((D/old).relative_to(R)),'envelope':ref,'payload':manifest['payload'],'raw_bytes':len(raw),'raw_sha256':manifest['raw_sha256'],'envelope_sha256':check[key+'_envelope_sha256'],'exit_code':1,'exact_roundtrip':True})
(D/'checks.json').write_text(json.dumps(checks,indent=2)+'\n')
canonical=R/'docs/exec-plans/reviews/HG-047/GENERAL.json';review=json.loads(canonical.read_text());assert review['reviewed_head_sha']==H and review['status']=='PASS'
review['evidence_refs']=[mapping.get(ref,ref) for ref in review['evidence_refs']]
for name in ['compact_conversion.py','compact-conversion.json']:
 ref=str((D/name).relative_to(R))
 if ref not in review['evidence_refs']:review['evidence_refs'].append(ref)
canonical.write_text(json.dumps(review,indent=2)+'\n')
report=(D/'REPORT.md').read_text().replace('`targeted.log`/`targeted.xml`','`targeted-log.json`/`targeted-xml.json`')
report+='\nThe failed targeted-run log and JUnit contain literal trailing whitespace. Before review persistence they were captured losslessly into compact envelopes (`targeted-log.json`, `targeted-xml.json`) and content-addressed gzip payloads. Raw SHA256 and byte counts match the untouched originals in /private/tmp, with exit 1 and the original JUnit start timestamp. No raw bytes were stripped or rewritten and no test was rerun for this storage-only correction. `compact-conversion.json` records both exact roundtrips. The originally executed finalization script remains historical; this subsequent script records the storage conversion.\n'
(D/'REPORT.md').write_text(report)
receipt={'reviewed_head_sha':H,'verdict_unchanged':'PASS','command':check['command'],'exit_code':1,'timestamp':stamp,'timestamp_source':'Original targeted JUnit testsuite timestamp','conversions':converted}
(D/'compact-conversion.json').write_text(json.dumps(receipt,indent=2)+'\n')
(D/'compact_conversion.py').write_bytes((T/'compact_conversion.py').read_bytes())
# Remove only uncommitted duplicate raw files after both exact roundtrips and reference updates.
for old in ['targeted.log','targeted.xml']:(D/old).unlink()
print(json.dumps(receipt,indent=2))
