"""Exact-Git index and manifest preservation review."""
from pathlib import Path
import json
import subprocess
from tools.harness.compact_evidence import envelope,digest
ROOT=Path(__file__).resolve().parents[5]
BASE='95ddd75d3eb410b7dffa15a1017276c504adc9a6'
HEAD='ceed78db431a348aae0b599a5e1b09bb082fb968'
def blob(path,rev=HEAD):
    return subprocess.check_output(['git','show',rev+':'+path],cwd=ROOT)
def load(path,rev=HEAD):
    return json.loads(blob(path,rev))
old=load('CURRENT_DOCUMENT_INDEX.json',BASE);new=load('CURRENT_DOCUMENT_INDEX.json')
expected=json.loads(json.dumps(old))
changed=[]
for group in ['documents','machine_readable']:
    assert len(new[group])==len(old[group])
    for i,entry in enumerate(old[group]):
        raw=blob(entry['path']);actual=new[group][i]
        assert actual['sha256']==digest(raw)
        if actual != entry:
            expected[group][i]['sha256']=digest(raw)
            changed.append(entry['path'])
assert expected==new
assert set(changed)=={'KineticLoop_Harness_Backlog_v0.2.json','KineticLoop_Harness_Traceability_v0.3.json','tools/harness/validate_harness.py'}
a=load('HARNESS_DOCUMENT_MANIFEST.json',BASE);b=load('HARNESS_DOCUMENT_MANIFEST.json')
assert {k:v for k,v in a.items() if k!='files'}=={k:v for k,v in b.items() if k!='files'}
assert [e['path'] for e in b['files'][:len(a['files'])]]==[e['path'] for e in a['files']]
refreshed=[]
for old,new in zip(a['files'],b['files']):
    raw=blob(old['path']);assert new['sha256']==digest(raw) and new['bytes']==len(raw)
    assert {k:v for k,v in old.items() if k not in ['sha256','bytes']}=={k:v for k,v in new.items() if k not in ['sha256','bytes']}
    if new!=old: refreshed.append(new['path'])
appended=b['files'][len(a['files']):]
for entry in appended:
    assert entry['path'].startswith('docs/exec-plans/evidence/HG-049/')
    raw=blob(entry['path']);assert entry['sha256']==digest(raw) and entry['bytes']==len(raw)
report={'status':'PASS','base_commit':BASE,'reviewed_head_sha':HEAD,'index_hash_only_refreshes':changed,'manifest_hash_byte_only_refreshes':refreshed,'manifest_own_evidence_appends':[e['path'] for e in appended],'executed_source_sha256':digest(Path(__file__).read_bytes())}
data=(json.dumps(report,indent=2)+'\n').encode();assert envelope(data) is None
(Path(__file__).parent/'METADATA.json').write_bytes(data)
print(json.dumps(report,indent=2))
