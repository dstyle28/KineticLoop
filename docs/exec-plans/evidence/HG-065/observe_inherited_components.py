"""Exact declared HG054 inherited-map component reads; no native full audit."""
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode=True
R=Path(__file__).resolve().parent
REPO = R.parents[3]
OUT = Path(os.environ['HG065_OBSERVATIONS'])
P='e8e93bd32a83bd2fd6bf89951863d59b37e9d2b3'
Q='3965cac382d333bd97f6c67fec8ecbe805b5932f'
O='9700a1b95d05c856897f74f125cfdf6fb3f6e646'


def run():
    start=time.monotonic_ns();reads=[];inputs=[];count=output_bytes=0
    def git(*args):
        nonlocal count,output_bytes
        if count>=16384 or time.monotonic_ns()-start>120000000000:raise ValueError('bounded-exhaustion')
        count+=1;p=subprocess.run(['git',*args],cwd=REPO,capture_output=True,timeout=10)
        output_bytes+=len(p.stdout)+len(p.stderr)
        if p.returncode or output_bytes>67108864:raise ValueError('bounded-git-denial')
        reads.append({'argv':['git',*args],'exit':p.returncode,'bytes':len(p.stdout),
                      'stdout_sha256':hashlib.sha256(p.stdout).hexdigest()})
        return p.stdout
    def obj(rev,path):
        rows=[x for x in git('ls-tree','-l','-z',rev,'--',path).split(b'\0') if x]
        assert len(rows)==1
        meta,name=rows[0].split(b'\t',1);mode,kind,oid,size=meta.split()
        assert name.decode()==path and mode in (b'100644',b'100755') and kind==b'blob' and int(size)<=8388608
        data=git('cat-file','blob',oid.decode());assert len(data)==int(size)
        snapshot='inputs/custody-native/'+rev+'/'+path  # provenance only; no snapshot copy
        item={'origin':{'kind':'IMMUTABLE_GIT_BLOB','revision':rev,'path':path,'mode':mode.decode(),'blob':oid.decode()},
              'snapshot':snapshot,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
        inputs.append(item);return data
    spec=importlib.util.spec_from_file_location('custody_inherited_protected_codec',REPO/'tools/harness/compact_evidence.py')
    n=importlib.util.module_from_spec(spec);spec.loader.exec_module(n);n.git=lambda root,*args:git(*args)
    path='docs/exec-plans/evidence/HG-054/collection-conversion/COMPACT_REENCODING.json'
    data=obj(O,path);assert obj(P,path)==data and obj(Q,path)==data
    record=n.reencoding_record(data);assert record['identity']=='HG-054'
    source=record['source_revision'];base=record['protected_base']
    git('merge-base','--is-ancestor',base,source);git('merge-base','--is-ancestor',source,O)
    components=[];decoded=0
    for ordinal,e in enumerate(record['entries']):
        metadata=[];raws=[];denials=[]
        for side,rev in [('original',source),('replacement',Q)]:
            b=e[side];envelope_data=obj(rev,b['envelope']['path']);payload_data=obj(rev,b['payload']['path'])
            for k,d in [('envelope',envelope_data),('payload',payload_data)]:
                assert n.snapshot_bytes(b[k]['path'],d)==b[k]
            m=n.envelope(envelope_data);metadata.append({k:m[k] for k in n.EXECUTION_FIELDS})
            raw=n.decode(payload_data,m[n.MARKER],m['raw_bytes']);assert n.digest(raw)==m['raw_sha256']
            decoded+=len(raw);assert decoded<=268435456
            raws.append(raw)
            try:
                assert n.read(REPO,b['envelope']['path'],rev)==raw
            except ValueError as ex:
                denials.append({'side':side,'path':b['envelope']['path'],'error':str(ex)})
        assert metadata[0]==metadata[1]==e['execution'] and raws[0]==raws[1]
        components.append({'ordinal':ordinal,'status':'OBSERVED_EXACT_SNAPSHOTS_METADATA_AND_RAW_BYTES',
                           'raw_bytes':len(raws[0]),'raw_sha256':n.digest(raws[0]),'native_reader_denials':denials})
    # Original declaration schemas, distinct from the observation schema.
    schemas=[]
    import yaml,jsonschema
    for rev,display in [(Q,'HG-058'),('337146e1927ba0f57995d4af26f4108cfc95d7a5','HG-059')]:
        schema_data=obj(rev,'HARNESS_CHANGE.schema.json')
        record_data=obj(rev,'docs/exec-plans/governance/'+display+'.yaml')
        original=yaml.safe_load(record_data);jsonschema.validate(original,json.loads(schema_data))
        schemas.append({'revision':rev,'identity':original['change_identity'],'change_status':original['change_status'],
                        'schema_sha256':hashlib.sha256(schema_data).hexdigest(),'result':'OBSERVED_ORIGINAL_SCHEMA_VALID'})
    out={'purpose':'DECLARED_INHERITED_MAP_COMPONENTS_ONLY','map_path':path,'owner':'HG-054',
         'source':source,'original_protected_base':base,'components':components,
         'original_declaration_schema_checks':schemas,'native_full_map_history_audit':'NOT_RUN',
         'all_map_inventory':'NOT_RUN','whole_storage_audit':'NOT_RUN','full_preimport_rerun':False,
         'historical_scripts_executed':False,'commands':reads,'git_operations':count,
         'git_output_bytes':output_bytes,'decoded_bytes':decoded,'elapsed_ns':time.monotonic_ns()-start}
    (OUT/'INHERITED_COMPONENT_OBSERVATIONS.json').write_text(json.dumps(out,separators=(',',':'))+'\n')
    (OUT/'INHERITED_GIT_INPUTS.json').write_text(json.dumps({'inputs':inputs},separators=(',',':'))+'\n')
    print(json.dumps({'entries':len(components),'native_reader_denials':sum(len(x['native_reader_denials']) for x in components),
                      'git_operations':count,'decoded_bytes':decoded,'full_native_audit':'NOT_RUN'}))


if __name__=='__main__':run()
