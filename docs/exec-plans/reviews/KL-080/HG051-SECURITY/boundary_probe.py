"""Supplemental read-only checks, including conservative credential pattern scan."""
import sys,json,re,hashlib,gzip,subprocess,xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path('/Users/davetian/.codex/worktrees/59e4/KineticLoop');HEAD='417b65ee68244dc86ab02add231b24dc662be790';BASE='1d3075151246b2774640a3d7acec836f47ab2b8d';TESTED='feb3236c175df171611fc5b7ddb4f6eeca3ce47c'
sys.path.insert(0,str(ROOT/'tools/harness'));import compact_evidence as ce
D='docs/exec-plans/evidence/KL-080/HG051-'+TESTED+'/'
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
def raw(p):return ce.read(ROOT,p,HEAD,tested=TESTED)
host=json.loads(git('show',HEAD+':docs/exec-plans/evidence/KL-080/HG051-hosted-index-correction/hosted-db-verification.json'))
col=json.loads(raw(host['raw_artifacts']['collection.json']['path']))
exe=json.loads(raw(host['raw_artifacts']['execution.json']['path']))
assert col['exit_code']==exe['exit_code']==0 and len(col['nodeids'])==len(set(col['nodeids']))==780
xml=ET.fromstring(raw(host['raw_artifacts']['database.xml']['path']))
actual={c.attrib['classname'].replace('.','/')+'.py::'+c.attrib['name'] for c in xml.findall('.//testcase')}
assert actual==set(col['nodeids'])
older=['test_deterministic_planning','test_full_action_preparation','test_full_test_execution','test_test_only_demo','test_factsets','test_preparation','test_protocol_interleavings','test_transaction_interfaces']
counts={name:sum(n.startswith('tests/db/'+name+'.py::') for n in actual) for name in older}
assert all(counts.values())
source=raw(D+'source_suite_dc.stdout.capture.json').decode();w=[json.loads(l.split('SOURCE_EVIDENCE ',1)[1]) for l in source.splitlines() if 'SOURCE_EVIDENCE ' in l]
trajectory=next(x for x in w if x['kind']=='kl080_owner_trajectory')
persisted=trajectory['persisted']
assert len(persisted['authorization_issuances'])==2
assert all(r[0]['decision']=='ELIGIBLE' for r in persisted['admission_decisions'])
assert all(r[0]['association_state']=='MATCHED' for r in persisted['event_association_decisions'])
assert all(r[0]['command_authority']=='NONE' for r in persisted['evidence_revisions'])
assert all(r[0]['typed_payload']['event_association_status']=='CONFIRMED' for r in persisted['evidence_resolutions'])
assert len(persisted['evidence_resolutions'])==2 and len(persisted['validation_results'])==1
patterns={
 'private_key':rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
 'github_token':rb'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,})\b',
 'openai_key':rb'\bsk-(?:proj-|svcacct-)[A-Za-z0-9_-]{40,}',
 'aws_access_key':rb'\bAKIA[0-9A-Z]{16}\b',
}
paths=git('diff','--name-only','--diff-filter=ACMRT',BASE,HEAD).decode().splitlines();seen=set();hits=[];scanned=0
for p in paths:
 b=git('show',HEAD+':'+p)
 if p.endswith('.gz'):b=gzip.decompress(b)
 h=hashlib.sha256(b).hexdigest()
 if h in seen:continue
 seen.add(h);scanned+=1
 for name,pattern in patterns.items():
  if re.search(pattern,b):hits.append({'path':p,'pattern':name})
assert not hits,hits
out={'reviewed_head_sha':HEAD,'hosted_unique_collected_and_executed_nodes':780,'junit_exact_node_set_match':True,'older_hosted_suite_counts':counts,'full_trajectory':{'issuances':2,'resolutions':2,'validation':1,'bindings':len(persisted['execution_bindings']),'S13':'ELIGIBLE','S12':'MATCHED','S36':'CONFIRMED','evidence_command_authority':'NONE'},'credential_scan':{'unique_changed_plain_or_decompressed_blobs':scanned,'patterns':list(patterns),'matches':hits,'limitation':'High-confidence pattern scan only; not proof of absence of every possible secret.'},'status':'PASS'}
Path(__file__).with_name('boundary-verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
