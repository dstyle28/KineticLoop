from pathlib import Path
import collections, hashlib, json, re, subprocess, xml.etree.ElementTree as ET
from _pytest.junitxml import mangle_test_address,bin_xml_escape
P=Path('/private/tmp/hg047-general-r4'); R=Path('/Users/davetian/.codex/worktrees/ffff/KineticLoop'); H='b71d2d63f8bc27ab0e905b0be8a0cea5f0122a91'; S='7b35dc5dd7c488b60651175574e37b5d9389d335'
def raw(name): return (P/('decoded-'+name)).read_bytes()
def obj(name): return json.loads(raw(name))
def sha(x): return hashlib.sha256(x).hexdigest()
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip()==H
receipt=obj('worker-receipt-json.json');final=obj('development-json.json'); initial=obj('development-initial-recovered-json.json')
assert receipt['head']==S and receipt['status']=='PASS' and receipt['container_removed'] and receipt['volume_removed']
assert receipt['full_database_required'] is False and final['full_db'] is False and final['test_only'] is True
assert not any(final[k] for k in ['app_object_created','signer_config_read','admission_read','publication'])
lookup={'development.json':'development-initial-recovered-json.json','worker/harness.xml':'worker--harness-xml.json','worker/unit.xml':'worker--unit-xml.json','worker/run/execution.json':'worker--run--execution-json.json'}
for path,digest in receipt['artifacts'].items():
 name=lookup.get(path,path.replace('.log','-log.json'));assert sha(raw(name))==digest,path
for check in receipt['checks']:
 assert check['exit_code']==0 and not check['interrupted']; log=raw(check['stdout']['path'].replace('.log','-log.json'))
 assert sha(log)==check['stdout']['sha256'] and len(log)==check['stdout']['bytes']
# Reconstruction justified by exact entire original byte hash, with only terminal metadata additions.
rebuilt=dict(final)
for k in ['image_environment','counts','duration_seconds_monotonic','finished_at']: rebuilt.pop(k)
rebuilt['status']='RUNNING'
assert rebuilt==initial and (json.dumps(rebuilt,indent=2)+'\n').encode()==raw('development-initial-recovered-json.json')
for asset,digest in final['controller_files'].items():
 assert sha(subprocess.check_output(['git','show',final['installed_reviewed_revision']+':tools/harness/'+asset],cwd=R))==digest
host=obj('host--checks-json.json')
for label,check in host['records'].items():
 log=raw('host--'+label+'-log.json');assert check['exit_code']==0 and sha(log)==check['sha256'] and len(log)==check['bytes']
nodes=[l for l in raw('host--collection-log.json').decode().splitlines() if l.startswith('tests/')]
obs=obj('worker--run--execution-json.json');assert obs['exit_code']==0 and obs['nodeids']==nodes and len(set(nodes))==1324
expected=[]
for node in nodes:
 parts=mangle_test_address(node);expected.append(('.'.join(parts[:-1]),bin_xml_escape(parts[-1])))
cases=list(ET.fromstring(raw('worker--harness-xml.json')).iter('testcase'))
assert collections.Counter(expected)==collections.Counter((c.get('classname'),c.get('name')) for c in cases)
assert all(not list(c) for c in cases)
# Determine historical previous failed worker directly from gzip artifacts.
import gzip
prefix='docs/exec-plans/evidence/HG-047/development-8a78241/'
manifest=json.loads(subprocess.check_output(['git','show',H+':'+prefix+'worker--harness-xml.json'],cwd=R))
failed=ET.fromstring(gzip.decompress(subprocess.check_output(['git','show',H+':'+manifest['payload']],cwd=R)))
oldcases=list(failed.iter('testcase')); errors=[{'classname':c.get('classname'),'name':c.get('name'),'error_type':c.find('error').get('type')} for c in oldcases if c.find('error') is not None]
# Avoid persisting huge parametrized names a second time, keep source evidence refs and identity hashes.
for e in errors: e['name_sha256']=sha(e.pop('name').encode())
out={'reviewed_head':H,'tested_commit':S,'status':'PASS','receipt_artifacts_verified':len(receipt['artifacts']),'worker_checks_verified':len(receipt['checks']),'host_checks_verified':len(host['records']),'installed_assets_sha_verified':len(final['controller_files']),'initial_receipt_exact_bytes_reconstructed':True,'final_metadata_separate_preserved':True,'container_removed_recorded':True,'volume_removed_recorded':True,'harness_unique_collection_observer_junit_equal':1324,'collection_identity_sha256':sha(json.dumps(nodes).encode()),'no_test_failures_errors_skips':True,'historical_failed_junit':{'reference':prefix+'worker--harness-xml.json','total':len(oldcases),'errors':errors},'limitations':['Cleanup verified from complete receipt and driver; no Docker calls in this review.','Full DB and final App gate remain NOT_RUN; no final merge recommendation.','Observer records session.items, not phase events; JUnit case identity corroborates completion.']}
(P/'execution-verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
