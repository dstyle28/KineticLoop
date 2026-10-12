"""Bounded read-only custody preparation. Never calls native full audits.

Only exact declared original-reference chains are inspected. Historical scripts
are data. The imported codec is current protected authority, isolated pure/read
functions only. This program is not an installed host operation or credential.
"""
from __future__ import annotations
import hashlib
import importlib.util
import json
import os
import subprocess
import time
from pathlib import Path
import yaml
from custody_study import Budget, custody_predicate
from source_fixture import original_sources

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
OUT = Path(os.environ['HG065_OBSERVATIONS'])
P = 'e8e93bd32a83bd2fd6bf89951863d59b37e9d2b3'
Q = '3965cac382d333bd97f6c67fec8ecbe805b5932f'
O = '9700a1b95d05c856897f74f125cfdf6fb3f6e646'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(name, value):
    (OUT/name).write_text(json.dumps(value,indent=2)+'\n')


def run():
    budget = Budget({'git_operations':16384,'git_output_bytes':67108864,'decoded_bytes':268435456,
                     'comparison_bytes':268435456,'commits':4096,'parent_edges':8192,'path_entries':65536})
    commands, new_inputs, observations = [], [], []
    objects, trees, graphs, parent_order = {}, {}, {}, {}

    def git(*args):
        budget.charge('git_operations',1)
        start = time.monotonic_ns()
        proc = subprocess.run(['git',*args],cwd=REPO,capture_output=True,timeout=10)
        budget.charge('git_output_bytes',len(proc.stdout)+len(proc.stderr))
        commands.append({'argv':['git',*args],'exit':proc.returncode,
                         'stdout_bytes':len(proc.stdout),'stdout_sha256':sha(proc.stdout),
                         'stderr_bytes':len(proc.stderr),'stderr_sha256':sha(proc.stderr),
                         'elapsed_ns':time.monotonic_ns()-start})
        if proc.returncode:
            raise ValueError('bounded-git-denial:'+repr(args)+':'+proc.stderr.decode(errors='replace'))
        return proc.stdout

    def tree(rev, paths):
        key=(rev,tuple(sorted(paths)))
        if key in trees:
            return trees[key]
        values={}
        for line in git('ls-tree','-l','-z',rev,'--',*sorted(paths)).split(b'\0'):
            if not line:
                continue
            meta, encoded = line.split(b'\t',1)
            mode,kind,oid,size=meta.split()
            name=encoded.decode()
            budget.charge('path_entries',1)
            if name not in paths or kind!=b'blob' or mode not in (b'100644',b'100755'):
                raise ValueError('bounded-tree-shape')
            values[name]={'path':name,'mode':mode.decode(),'blob':oid.decode(),'bytes':int(size)}
        trees[key]=values
        return values

    def obj(rev,path):
        key=(rev,path)
        if key in objects:
            return objects[key]
        item=tree(rev,[path])[path]
        if item['bytes']>8388608:
            raise ValueError('stored-bound')
        data=git('cat-file','blob',item['blob'])
        assert len(data)==item['bytes']
        item=dict(item,sha256=sha(data))
        snap='inputs/custody-native/'+rev+'/'+path
        # Original Git bytes remain in Git, never copied into task evidence.
        new_inputs.append({'origin':{'kind':'IMMUTABLE_GIT_BLOB','revision':rev,'path':path,
                                     'mode':item['mode'],'blob':item['blob']},
                           'snapshot':snap,'sha256':item['sha256'],'bytes':len(data)})
        objects[key]=(item,data)
        return item,data

    source=REPO/'tools/harness/compact_evidence.py'
    spec=importlib.util.spec_from_file_location('custody_protected_codec',source)
    native=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(native)
    native.git=lambda root,*args:git(*args)
    old_group=json.loads((ROOT/'FIXTURE_INPUTS.json').read_bytes())['group']
    prior=json.loads((ROOT/'FIXTURE_INPUTS.json').read_bytes())['closure']
    D=prior['delivery']['commit'];B,J=prior['delivery']['parents'];F=prior['delivery']['original_record_revision']
    group_paths=sorted({m['path'] for m in old_group['members']}|set(old_group['payload_paths']))
    objects_at_q={p:obj(Q,p)[0] for p in group_paths}
    declarations={}
    for display,rev in [('HG-058',Q),('HG-059',F)]:
        declaration_path='docs/exec-plans/governance/'+display+'.yaml'
        binding,data=obj(rev,declaration_path)
        record=yaml.safe_load(data)
        assert record['change_identity']=='harness-governance-v0.1/'+display
        refs={}
        for field in ('files_changed','evidence_refs'):
            for n,ref in enumerate(record.get(field,[])):
                refs.setdefault(ref,[]).append(field+'/'+str(n))
        for n,check in enumerate(record['checks_run']):
            refs.setdefault(check['evidence_ref'],[]).append('checks_run/'+str(n)+'/evidence_ref')
        declarations[display]=(rev,binding,refs,record['change_status'])

    packet_binding,packet=obj(P,'docs/exec-plans/active/HG-058.md')
    assert all(pin.encode() in packet for pin in (Q,O,'harness-governance-v0.1/HG-058'))
    observations.append({'id':'protected-original-task-pins','status':'OBSERVED_EXACT_PINS',
                         'object':packet_binding,'original_selected':Q,'original_base':O})
    assert git('rev-list','--parents','-n','1',D).decode().split()==[D,B,J]
    for ancestor,descendant in [(F,J),(D,P),(D,Q),(O,P)]:
        git('merge-base','--is-ancestor',ancestor,descendant)
    observations.append({'id':'foreign-normal-delivery','status':'OBSERVED_CORRECT_TWO_PARENT_ORIENTATION',
                         'commit':D,'parents':[B,J],'original_declaration':F})

    # Preserve the old declared 33/37 interval, and additionally bind the direct
    # declared foreign introduction-to-delivery chain. No unrelated historical hunt.
    introduction_by_path={
        old_group['members'][0]['path']:Q,
        old_group['members'][1]['path']:'c104d777588d9da0fa400314eab904a650c08b48',
        old_group['members'][2]['path']:F,
        old_group['members'][3]['path']:'8368779f9870f92a46ae22b316fff37408d49b5f',
        old_group['members'][4]['path']:'74c93c06e83cd5087ecd3b4cc11320b88b246616',
        old_group['members'][5]['path']:'09c11d71b4e10dc14040ae2a85736b4d6f0ac810'}
    for p in old_group['payload_paths']:
        introduction_by_path[p]=('c104d777588d9da0fa400314eab904a650c08b48' if '/HG-058/' in p
                                 else '09c11d71b4e10dc14040ae2a85736b4d6f0ac810')
    old_edges=set();old_vertices=set()
    interval_edges=set();interval_vertices=set()

    def graph(start,end,paths,label):
        key=(start,end,tuple(paths))
        if key in graphs:
            return graphs[key]
        git('merge-base','--is-ancestor',start,end)
        rows=git('rev-list','--ancestry-path','--parents',start+'..'+end).decode().splitlines()
        start_parents=git('rev-list','--parents','-n','1',start).decode().split()
        data=[r.split() for r in rows]+[start_parents]
        for row in data:parent_order[row[0]]=row[1:]
        vertices={r[0] for r in data};edges={(p,r[0]) for r in data for p in r[1:]}
        budget.charge('commits',len(vertices));budget.charge('parent_edges',len(edges))
        all_nodes=vertices|{p for p,c in edges}
        states={rev:tree(rev,paths) for rev in sorted(all_nodes)}
        graphs[key]=(vertices,edges,states)
        interval_edges.update(edges);interval_vertices.update(vertices)
        observations.append({'id':label,'start':start,'end':end,'vertices':len(vertices),
                             'all_edges_with_incoming_boundaries':len(edges)})
        return graphs[key]

    # Exact old interval counts exclude incoming edges at the origin, as before;
    # new path proofs include these incoming boundaries and pre-D introductions.
    for old in prior['graph']:
        verts,edges,states=graph(old['origin'],old['end'],sorted(old['baseline']),'preserved-'+old['kind'])
        old_vertices.update(verts)
        old_edges.update((p,c) for p,c in edges if c!=old['origin'])
    assert len(old_vertices)==33 and len(old_edges)==37

    path_histories={}
    for p in group_paths:
        intro=introduction_by_path[p]
        endpoints=([Q] if '/HG-058/' in p else [P,Q])
        nodes,edges={},set()
        for end in endpoints:
            verts,es,states=graph(intro,end,[p],'original-path-'+p.rsplit('/',1)[-1]+'-'+end[:8])
            edges.update(es)
            for rev,entries in states.items():
                val=entries.get(p)
                if val is not None:
                    assert {k:val[k] for k in ('path','mode','blob','bytes')}=={
                        k:objects_at_q[p][k] for k in ('path','mode','blob','bytes')}
                    val=objects_at_q[p]
                nodes[rev]=val
        imports={}
        for parent,child in sorted(edges):
            if nodes[parent] is None and nodes[child] is not None and child!=intro:
                assert '/HG-059/' in p
                parents=git('rev-list','--parents','-n','1',child).decode().split()[1:]
                assert len(parents)==2 and nodes[parents[0]] is None and nodes[parents[1]]==objects_at_q[p]
                git('merge-base','--is-ancestor',D,child)
                if child!=D:git('merge-base','--is-ancestor',D,parents[1])
                imports[child]=parents
        path_histories[p]={'path':p,'original':objects_at_q[p],
                           'nodes':nodes,'edges':[list(e) for e in sorted(edges)],'imports':imports,
                           'parents':{child:parent_order[child] for child in sorted({c for p,c in edges})},
                           'boundaries':sorted(set(nodes)-{c for p,c in edges})}

    raw_by_path={};native_reads=[];members=[]
    for original in old_group['members']:
        p=original['path'];e,data=obj(Q,p);manifest=native.envelope(data)
        assert manifest is not None
        raw=native.read(REPO,p,Q)
        budget.charge('decoded_bytes',len(raw));budget.charge('comparison_bytes',len(raw))
        assert sha(raw)==manifest['raw_sha256'] and len(raw)==manifest['raw_bytes']
        native_reads.append({'path':p,'status':'OBSERVED_NATIVE_CODEC_AND_CLASSIFIER_RETURNED_ORDINARY',
                             'raw_sha256':sha(raw),'raw_bytes':len(raw)})
        raw_by_path[p]=raw
        display=p.split('/')[3];rev,binding,refs,status=declarations[display]
        assert p in refs
        protected=tree(P,[p]).get(p)
        if display=='HG-058':assert protected is None
        else:assert protected=={k:e[k] for k in ('path','mode','blob','bytes')}
        for snapshot in ([F,J,D,P] if display=='HG-059' else [introduction_by_path[p]]):
            assert obj(snapshot,p)[0]==e
            assert obj(snapshot,manifest['payload'])[0]==objects_at_q[manifest['payload']]
        members.append({'envelope':e,'payload':objects_at_q[manifest['payload']],
                        'raw_sha256':sha(raw),'raw_bytes':len(raw),
                        'declaration':{'identity':'harness-governance-v0.1/'+display,'revision':rev,
                                       'object':binding,'pointers':refs[p],'ref':p,
                                       'authority_chain':('PROTECTED_PACKET_FROZEN_ORIGINAL' if display=='HG-058'
                                                          else 'NORMAL_FOREIGN_DELIVERY_ORIGINAL')},
                        'introduction':introduction_by_path[p],'history':path_histories[p],
                        'payload_introduction':introduction_by_path[manifest['payload']],
                        'payload_history':path_histories[manifest['payload']],
                        'protected_state':'ABSENT' if protected is None else 'EXACT_ORIGINAL',
                        'representation':{'codec':manifest['kineticloop_evidence'],
                                          'raw_sha256':sha(raw),'raw_bytes':len(raw),
                                          'stored_sha256':manifest['stored_sha256'],'stored_bytes':manifest['stored_bytes'],
                                          'raw_bytes_equal':'OBSERVED_EXACT_BYTES',
                                          'native_read_observation':native_reads[-1]['status']}})
    assert len(set(raw_by_path.values()))==1
    inv_rows=[{'path':p} for p in json.loads((ROOT/'FIXTURE_INPUTS.json').read_bytes())['inventory_paths']]
    # Exact eight-path intersection and complete two-directory enumeration; original
    # native whole-inventory decoding is intentionally NOT rerun here.
    inv_paths={x['path'] for x in inv_rows}
    assert set(group_paths)<=inv_paths
    directory_rows=[]
    for directory in sorted({str(Path(p).parent) for p in group_paths}):
        for rev in [Q,P]:
            out=git('ls-tree','-rl','-z',rev,'--',directory)
            entries=[]
            for line in out.split(b'\0'):
                if not line:continue
                meta,p=line.split(b'\t',1);mode,kind,oid,size=meta.split()
                entries.append({'path':p.decode(),'mode':mode.decode(),'blob':oid.decode(),'bytes':int(size)})
            directory_rows.append({'revision':rev,'directory':directory,'entries':entries})
            exact_payloads=[x['path'] for x in entries if x['blob']=='75ff3b4ff50f3118b78e015130418142a0fdab31']
            assert sorted(exact_payloads)==sorted(p for p in old_group['payload_paths'] if str(Path(p).parent)==directory
                                                       and ('/HG-059/' in p or rev==Q))

    map_path='docs/exec-plans/evidence/HG-058/recovery-conversion/COMPACT_REENCODING.json'
    C='d1c1411eae72cbc3499e5fbdc8a266dfde19d003'
    map_obj,map_data=obj(Q,map_path);mapping=native.reencoding_record(map_data)
    assert obj(C,map_path)[1]==map_data
    A=mapping['source_revision'];assert mapping['protected_base']==O and mapping['identity']=='HG-058'
    for a,b in [(O,A),(A,C),(C,Q)]:git('merge-base','--is-ancestor',a,b)
    assert git('merge-base','--all',C,P).decode().splitlines()==[O]
    map_parents=git('rev-list','--parents','-n','1',C).decode().split()[1:]
    assert all(not tree(parent,[map_path]) for parent in map_parents)
    assert not tree(O,[map_path]) and not tree(P,[map_path])
    mapped_paths=set();map_snapshots=[]
    for entry in mapping['entries']:
        original_fields=None
        for side,rev in [('original',A),('replacement',Q)]:
            binding=entry[side]
            for kind in ('envelope','payload'):
                expected=binding[kind];bound,data=obj(rev,expected['path']);mapped_paths.add(expected['path'])
                assert native.snapshot_bytes(expected['path'],data)==expected
                map_snapshots.append({'revision':rev,'object':bound,'status':'OBSERVED_NATIVE_SNAPSHOT_MATCH'})
            metadata=native.envelope(obj(rev,binding['envelope']['path'])[1])
            fields={k:metadata[k] for k in native.EXECUTION_FIELDS}
            if original_fields is None:original_fields=fields
            assert fields==original_fields==entry['execution']
        before=native.read(REPO,entry['original']['envelope']['path'],A)
        after=native.read(REPO,entry['replacement']['envelope']['path'],Q)
        assert before==after
        budget.charge('decoded_bytes',len(before)+len(after));budget.charge('comparison_bytes',len(before)+len(after))
    assert not mapped_paths.intersection(group_paths)
    observations.append({'id':'own-map-original-admission-source-snapshots','status':'OBSERVED_BOUNDED_COMPONENT_FACTS',
                         'map':map_obj,'source':A,'admission':C,'snapshot_checks':map_snapshots,
                         'native_retained_map_function':'NOT_RUN_RECURSIVELY_REQUIRES_FULL_AUDIT',
                         'inherited_map_full_audit':'NOT_RUN'})
    proof={'selected_identity':'harness-governance-v0.1/HG-058','original_base':O,'protected_base':P,
           'original_selected':Q,'members':members,'physical_paths':[objects_at_q[p] for p in group_paths],
           'inventory_intersection':group_paths,
           'delivery':{'commit':D,'parents':[B,J],'original_record':F,'foreign_owner':'HG-059',
                       'relation_observations':['ORIGINAL_RECORD_TO_PR_HEAD','DELIVERY_TO_PROTECTED','DELIVERY_TO_SELECTED','CORRECT_PARENT_ORIENTATION']},
           'map_binding':{'object':map_obj,'identity':'HG-058','original_base':O,'source':A,'admission':C,
                          'member_relationship':'UNCHANGED_UNMAPPED_ORDINARY_REPRESENTATION','native_full_audit':'NOT_RUN'}}
    result=custody_predicate(proof,original_sources=original_sources(ROOT))
    assert result['representations']==6 and result['physical_paths']==8 and result['physical_bytes']==12746
    elapsed=time.monotonic_ns()-budget.start
    write('ACTUAL_CUSTODY_PROOF.json',proof)
    write('ACTUAL_PREPARATION_DISPOSITION.json',{'purpose':'AUTHOR_IMMUTABLE_DATA_CUSTODY_STUDY_ONLY',
          'result':result,'observations':observations,'native_reads':native_reads,'directory_bindings':directory_rows,
          'old_declared_interval':{'vertices':len(old_vertices),'edges':len(old_edges)},
          'expanded_original_path_intervals':{'vertices':len(interval_vertices),'edges_with_boundaries':len(interval_edges)},
          'native_whole_inventory_decode':'NOT_RUN','old_full_audit_reexecuted':False,
          'full_native_live_runtime':'NOT_RUN','private_host_entry':'NOT_RUN','independent_review':'NOT_RUN',
          'scope':'DECLARED_GROUP_AND_TWO_DIRECTORY_CLOSURE; PRESERVED_ORIGINAL_INVENTORY_INTERSECTION',
          'consumed':budget.used,'elapsed_ns':elapsed,'source_codec_sha256':sha(source.read_bytes()),
          'historical_execution_attribution':'UNVERIFIED','child_exit_6358':None,'driver_exit_6358':143})
    write('IMMUTABLE_COMMAND_READS.json',{'commands':commands,'full_audit_run':False,'historical_scripts_executed':False,
                                        'elapsed_ns':elapsed,'consumed':budget.used})
    write('NEW_GIT_INPUTS.json',{'inputs':new_inputs})
    print(json.dumps({'status':result['status'],'six_envelopes':6,'physical_paths':8,'physical_bytes':12746,
                      'git_reads':len(commands),'elapsed_ns':elapsed,'native_full_audit':'NOT_RUN'}))


if __name__=='__main__':
    run()
