'Non-operational definition fixtures. NEVER a production authority API.\n\nAll OraclePremise values are synthetic independently generated test premises.\nNo function authenticates, installs, admits, imports Git history or executes gates.\n'
from __future__ import annotations
import copy,hashlib,json,re,time
from pathlib import Path
import jsonschema
import native_fixture as nf
D=Path(__file__).resolve().parent
PHASE=json.loads((D/'PHASE_MATRIX.json').read_bytes())
OWN=json.loads((D/'CHECK_OWNERSHIP.json').read_bytes())
LIMITS=json.loads((D/'BUDGETS.json').read_bytes())['incorporated_original']['incremental_work_limits']
PRESCHEMA=json.loads((D/'PREIMPORT_SCHEMA.json').read_bytes())
PUBSCHEMA=json.loads((D/'PUBLIC_DENIAL_SCHEMA.json').read_bytes())
ROLES={p:('AUTHOR' if p in ['STAGE_FROZEN','STAGE_CHECKS','BASE_IMPORT','STABLE_T','AUTHOR_CHECKS','RESULT_R','REVIEW_SUFFIX'] else 'ROOT') for p in PHASE['ordered_phases']}
FINAL_SCHEMA=json.loads((D/'MULTI_OUTPUT_SCHEMA.json').read_bytes())
class Denial(ValueError): pass

def sh(value): return hashlib.sha256(value if type(value) is bytes else json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def require(condition,reason):
    if not condition:raise Denial(reason)
def exact(actual,expected):
    require(type(actual) is type(expected),'BUILTIN_TYPE_MISMATCH')
    if type(expected) is dict:
        require(actual.keys()==expected.keys(),'UNKNOWN_OR_MISSING_FIELD')
        for k in expected:exact(actual[k],expected[k])
    elif type(expected) is list:
        require(len(actual)==len(expected),'CARDINALITY_MISMATCH')
        for a,b in zip(actual,expected):exact(a,b)
    else:require(actual==expected,'INDEPENDENT_FACT_MISMATCH')

def structure(value):
    # Reserve proposed children before pending allocation; same narrower definition caps.
    stack=[(value,0)];processed=0;string_chars=0
    while stack:
        v,depth=stack.pop();processed+=1
        require(depth<=32 and processed<=65536,'STRUCTURE_LIMIT')
        require(type(v) in (dict,list,str,int,bool,type(None)),'NON_JSON_TYPE')
        if type(v) is list:require(len(v)<=512,'LIST_LIMIT')
        child_count=2*len(v) if type(v) is dict else len(v) if type(v) is list else 0
        require(processed+len(stack)+child_count<=65536,'PENDING_LIMIT')
        if type(v) is str:
            string_chars+=len(v);require(string_chars<=262144,'STRING_BYTE_PREFLIGHT')
        children=([x for pair in v.items() for x in pair] if type(v) is dict else v if type(v) is list else [])
        stack.extend((c,depth+1) for c in children)
    encoded=json.dumps(value,separators=(',',':')).encode()
    require(len(encoded)<=262144,'JSON_BYTE_LIMIT')

def fixture_scope(path,phase='STAGING'):
    require(type(path) is str and 0<len(path)<=1024,'PATH_TYPE')
    require(re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*',path) is not None,'PATH_GRAMMAR')
    require(all(c not in ('.','..') for c in path.split('/')),'PATH_TRAVERSAL')
    allowed=PHASE['staging_paths'] if phase=='STAGING' else json.loads((D/'SCOPE_CORRECTION.json').read_bytes())['proposed']
    return any(path==p if not p.endswith('/**') else path.startswith(p[:-2]) for p in allowed)

class FixtureBudget:
    'Synthetic clock/counter observer; no host capabilities.'
    def __init__(self,clock=None):
        self.clock=clock or time.monotonic_ns;self.start=self.clock();self.used={k:0 for k in LIMITS};self.elapsed=0;self.reservation_failed=False
    def reserve(self,field,amount,pending=0):
        require(field in LIMITS and type(amount) is int and amount>=0 and type(pending) is int and pending>=0,'INVALID_RESERVATION')
        if self.used[field]+pending+amount>LIMITS[field]:
            self.reservation_failed=True;raise Denial('RESERVATION_LIMIT')
        require(not self.reasons(),'RESERVATION_DEADLINE_OR_LIMIT')
    def observe(self,field,amount):
        require(field in LIMITS and type(amount) is int and amount>=0,'INVALID_CHARGE')
        self.used[field]+=amount
        # Actual charge is retained even when its reservation fails; nothing positive survives.
        self.reasons()
    def reasons(self):
        self.elapsed=max(0,self.clock()-self.start)
        r=[]
        if self.reservation_failed or any(self.used[k]>v for k,v in LIMITS.items()):r.append('LIMIT_EXHAUSTED')
        if self.elapsed>120000000000:r.append('DEADLINE_EXCEEDED')
        return r

def fixture_group_binding(objects,key):
    'Synthetic ORIGINAL member rows fixed when constructing a test world.\n\n    This helper is not a native declaration resolver or a credential constructor.\n    Runtime derivation remains installed-only with original declarations/history.\n    '
    refs={x['payload'] for x in objects if x['kind']=='ENVELOPE' and x['raw_key']==key}
    return copy.deepcopy([x for x in objects if (x['kind']=='ENVELOPE' and x['raw_key']==key) or x['path'] in refs])

def fixture_inventory_oracle(objects,bodies,retained_groups=None,object_bytes=None):
    'Complete native ordinary representation model with independent byte pins.\n\n    Pinned native codec/classifier/read run over synthetic immutable blobs. Commit\n    resolution/ancestry are simulated, NOT native history or runtime credentials.\n    Both evidence/reviews and declared gzip-v1/xz-v1 are included without filtering.\n    Ordinary plain bytes participate in the exact native duplicate traversal.\n    '
    structure(objects);structure(bodies);structure(object_bytes)
    require(type(objects) is list and 0<len(objects)<=4096,'INVENTORY_MISSING')
    require(type(bodies) is dict and type(object_bytes) is dict,'INDEPENDENT_BYTE_BINDINGS_REQUIRED')
    require(all(type(x) is dict and type(x.get('path')) is str for x in objects),'OBJECT_FIELDS')
    require([x['path'] for x in objects]==sorted(x['path'] for x in objects),'INVENTORY_ORDER')
    require(len({x['path'] for x in objects})==len(objects),'INVENTORY_ALIAS')
    require(set(object_bytes)=={x['path'] for x in objects},'PHYSICAL_BYTE_INVENTORY')
    expected_fields={'path','mode','kind','bytes','sha256','raw_key','payload','codec','native_errors'}
    total=0;bulk={};duplicates=[];payload_refs=set();groups={};captures=0;index={x['path']:x for x in objects};data={}
    # Independently bind EVERY actual physical object before representation traversal.
    for x in objects:
        require(set(x)==expected_fields,'OBJECT_FIELDS')
        require(x['mode'] in ['100644','100755'],'NONREGULAR')
        require(type(x['bytes']) is int and x['bytes']>=0,'BYTE_TYPE')
        require(type(x['native_errors']) is list and not x['native_errors'],'NATIVE_ERROR')
        require(type(x['sha256']) is str and re.fullmatch('[0-9a-f]{64}',x['sha256']) is not None,'OBJECT_HASH')
        require(len(x['path'])<=1024,'PATH')
        try:
            nf.native.owner(x['path']);data[x['path']]=bytes.fromhex(object_bytes[x['path']])
        except (ValueError,TypeError):raise Denial('PATH_OR_INDEPENDENT_BYTES')
        require(len(data[x['path']])==x['bytes'] and sh(data[x['path']])==x['sha256'],'PHYSICAL_BYTE_MISMATCH')
        total+=x['bytes'];require(total<=nf.native.TOTAL_LIMIT,'TOTAL_BYTES')
    for x in objects:
        raw=None
        try:
            if x['kind']=='PAYLOAD':
                require(x['raw_key'] is None and x['payload'] is None and x['codec'] in nf.native.CODECS,'PAYLOAD_FIELDS')
                require(x['path'].endswith(nf.native.CODECS[x['codec']]),'PAYLOAD_CODEC_EXTENSION')
                require(x['bytes']<=nf.native.STORED_LIMIT,'STORED_LIMIT');continue
            require(not x['path'].endswith(tuple(nf.native.CODECS.values())),'NONPAYLOAD_STORAGE_PATH')
            require(x['bytes']<=nf.native.PLAIN_LIMIT,'PLAIN_LIMIT')
            require(Path(x['path']).name!='complete-diff.patch','FULL_DIFF_COPY')
            meta=nf.native.envelope(data[x['path']])
            if x['kind']=='ENVELOPE':
                captures+=1;require(captures<=LIMITS['captures'],'CAPTURE_LIMIT')
                require(meta is not None and meta.get(nf.native.MARKER) in nf.native.CODECS,'ORDINARY_ENVELOPE_REQUIRED')
                require(x['codec']==meta[nf.native.MARKER],'DECLARED_CODEC_BINDING')
                require(x['payload']==meta['payload'] and x['raw_key']==meta['raw_sha256'],'ENVELOPE_ROW_BINDING')
                require(x['payload'] in index and index[x['payload']]['kind']=='PAYLOAD' and index[x['payload']]['codec']==x['codec'],'PAYLOAD_ROW_BINDING')
                raw=nf.read_synthetic(x['path'],objects,object_bytes)
                require(x['raw_key'] in bodies and bytes.fromhex(bodies[x['raw_key']])==raw,'RAW_CORRUPTION')
                payload_refs.add(x['payload']);physical=x['payload']
            else:
                require(x['kind']=='PLAIN' and x['codec'] is None and x['raw_key'] is None and x['payload'] is None,'PLAIN_FIELDS')
                require(meta is None,'PLAIN_RESERVED_CLASSIFICATION');raw=data[x['path']];physical=x['path']
                try:value=json.loads(raw,object_pairs_hook=nf.native.unique)
                except (UnicodeError,json.JSONDecodeError):value=None
                require(not nf.native.embedded_raw(value),'EMBEDDED_RAW')
            require(not raw.lstrip().startswith(b'diff --git '),'FULL_DIFF_COPY')
        except (ValueError,KeyError,TypeError,UnicodeError) as ex:raise Denial(str(ex))
        if len(raw)>=16384:
            key=sh(raw);groups.setdefault(key,[]).append(x)
            # Match native error-before-update behavior: a duplicate leaves the
            # first physical prior unchanged, including plain -> envelope order.
            if key in bulk and (x['kind']=='PLAIN' or bulk[key]!=physical):duplicates.append(x['path']+':duplicate-bulk:'+bulk[key])
            else:bulk[key]=physical
    require(payload_refs=={x['path'] for x in objects if x['kind']=='PAYLOAD'},'UNREFERENCED_OR_MISSING_PAYLOAD')
    collisions={k:rows for k,rows in groups.items() if len({x['payload'] if x['kind']=='ENVELOPE' else x['path'] for x in rows})>1}
    require(len(collisions)<=LIMITS['groups'],'GROUP_LIMIT');preserved=set()
    if retained_groups is not None:
        structure(retained_groups);require(type(retained_groups) is dict,'RETAINED_GROUP_FIELDS')
        require(set(retained_groups)==set(collisions),'UNEXPECTED_OR_MISSING_COLLISION_GROUP')
        for key,rows in collisions.items():
            require(all(x['kind']=='ENVELOPE' for x in rows),'PLAIN_BULK_COPY')
            owners={x['path'].split('/')[3] for x in rows};require(2<=len(owners)<=len(rows)<=512,'GROUP_CARDINALITY')
            by_owner={}
            for x in rows:by_owner.setdefault(x['path'].split('/')[3],set()).add(x['payload'])
            require(all(len(v)==1 for v in by_owner.values()),'MULTIPLE_OWNER_PAYLOADS')
            paths={x['path'] for x in rows}|{x['payload'] for x in rows};actual=[x for x in objects if x['path'] in paths]
            exact(actual,retained_groups[key]);preserved.update(paths)
    return {'files':len(objects),'stored_bytes':total,'digest':sh(objects),'errors':sorted(set(duplicates)),'preserved_paths':len(preserved),'preserved_bytes':sum(x['bytes'] for x in objects if x['path'] in preserved),'retained_groups_complete':retained_groups is not None}

def fixture_public_assertion(child,oracle,roots):
    structure(child);structure(oracle)
    require(oracle.get('retained_groups_complete') is True,'UNBOUND_COLLISION_REGRESSION')
    require(type(child['exit_code']) is int and child['exit_code']!=0,'CHILD_NOT_NONZERO')
    require(child['complete'] is True and child['timeout'] is False and child['interrupted'] is False,'CHILD_INCOMPLETE')
    require(set(child)=={'exit_code','complete','timeout','interrupted','command','tested','stdout','stderr'},'CHILD_FIELDS')
    require(child['command']==roots['public_child_command'] and child['tested']==roots['tested'],'CHILD_BINDING')
    try:
        raw=child['stdout'].encode('utf8')
        def pairs(rows):
            d={}
            for k,v in rows:
                require(k not in d,'DUPLICATE_KEY');d[k]=v
            return d
        report=json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(Denial('NONFINITE')))
    except (ValueError,UnicodeError):raise Denial('INVALID_NATIVE_REPORT')
    structure(report)
    expected={'identity':roots['identity'].split('/')[-1],'base':roots['original'],'head':roots['tested'],'stored_bytes':oracle['stored_bytes'],'files':oracle['files'],'inventory_sha256':oracle['digest'],'native_complete':True,'errors':oracle['errors'],'remedy':'python tools/harness/compact_evidence.py capture --help'}
    exact(report,expected);require(bool(oracle['errors']),'NO_EXPECTED_DENIAL')
    require(child['stderr']=='','UNEXPECTED_STDERR')
    out={'type':'PUBLIC_ORIGINAL_DENIAL_REGRESSION_V1','tested_commit':roots['tested'],'original_base':roots['original'],'child_command':child['command'],'child_exit_code':child['exit_code'],'child_complete':True,'enclosing_exit_code':0,'child_result':'EXPECTED_NATIVE_DENIAL','inventory_digest':oracle['digest'],'inventory_files':oracle['files'],'inventory_bytes':oracle['stored_bytes'],'derived_errors':oracle['errors'],'child_stdout_sha256':sh(raw),'child_stderr_sha256':sh(child['stderr'].encode()),'private_dispatch':False,'acceptance_eligible':False,'execution_reuse':False}
    jsonschema.validate(out,PUBSCHEMA);return out

def fixture_preimport_output(bindings,inventory,budget,disposition,completed=True,native_denial=False,unperformed=False):
    'Synthetic output/finalization model, never operation readiness authority.'
    require(set(disposition)=={'paths','bytes'} and all(type(v) is int and v>=0 for v in disposition.values()),'DISPOSITION_SHAPE')
    require(disposition['paths']<=inventory['files'] and disposition['bytes']<=inventory['stored_bytes'],'DISPOSITION_INVENTORY')
    why=budget.reasons()
    if unperformed:why=why or ['UNPERFORMED']
    if not completed and not unperformed:why.append('INCOMPLETE_CONTEXT')
    if native_denial:why.append('NATIVE_GUARD_DENIED')
    status='PREIMPORT_PRESERVATION_OBSERVED' if not why else 'PREIMPORT_UNPERFORMED' if why==['UNPERFORMED'] else 'PREIMPORT_DENIED'
    out={**bindings,'type':'RETAINED_REPRESENTATION_PREIMPORT_V1','status':status,'phase':'PREIMPORT_K','complete':completed and not unperformed and not any(x in why for x in ['LIMIT_EXHAUSTED','DEADLINE_EXCEEDED','INCOMPLETE_CONTEXT']),'ready_for_exact_import':not why,'inventory':inventory if not unperformed else {'digest':None,'files':0,'stored_bytes':0,'maps':0,'edges':0},'preserved_duplicate_paths':disposition['paths'] if not why else 0,'preserved_duplicate_bytes':disposition['bytes'] if not why else 0,'original_guard_status':'NOT_RUN' if unperformed else 'PARTIAL' if not completed else 'ALL_NATIVE_OBSERVED','live_guard_status':'NOT_RUN','selected_final_status':'NOT_RUN','admission_status':'NOT_RUN','app_status':'NOT_RUN','execution_attribution':'UNVERIFIED','acceptance_eligible':False,'execution_reuse':False,'host_exit_code':None if unperformed or not completed else 1 if why else 0,'driver_exit_code':None,'denial_reasons':sorted(set(why)),'elapsed_ns':budget.elapsed,'consumed':dict(budget.used)}
    # Two independent final observations, including on ordinary denial.
    for _ in range(2):
        late=budget.reasons();out['elapsed_ns']=budget.elapsed;out['consumed']=dict(budget.used)
        if late:
            out.update(status='PREIMPORT_DENIED',complete=False,ready_for_exact_import=False,preserved_duplicate_paths=0,preserved_duplicate_bytes=0,host_exit_code=1 if completed else None)
            out['denial_reasons']=sorted(set(out['denial_reasons']+late)-{'UNPERFORMED'})
    structure(out);jsonschema.validate(out,PRESCHEMA);return out

def fixture_preimport_bindings(roots):
    return {'invocation_id':'synthetic-root-one','repository':'neutral/project','selected_identity':roots['identity'],'original_base':roots['original'],'protected_base':roots['protected'],'original_selected':roots['original_selected'],'predecessor':roots['bootstrap'],'tree':roots['bootstrap_tree'],'installed_release':roots['bootstrap'],'controller':roots['controller'],'authority_digest':roots['authority']}

def fixture_bundle(roots,phase):
    revision=roots['bootstrap'] if phase=='K' else roots['final']
    rows=[{'path':a,'source_revision':revision,'source_path':'tools/harness/'+a,'mode':'100644','bytes':100+n,'sha256':sh((a+revision).encode())} for n,a in enumerate(PHASE['assets'])]
    files={r['path']:r['sha256'] for r in rows}
    return {'installed_commit':revision,'assets':rows,'controller_files':files,'controller':hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest(),'authority':roots['authority'],'policy':roots['policy'],'image':roots['image'],'source_tree':roots['bootstrap_tree'] if phase=='K' else roots['final_tree']}

def fixture_author_checks(roots):
    rows=[]
    for i,r in enumerate(OWN['author_required']):
        cmd=r['command_template'].format(P=roots['protected'],T=roots['tested'],O=roots['original'],unique_scratch='/private/tmp/synthetic-final-one')
        nodes=[f'positive-{r['check_id']}'] if r['positive_identity_obligation'].startswith('COLLECTION') else []
        rows.append({'check_id':r['check_id'],'command':cmd,'tested':roots['tested'],'evidence_revision':roots['result'],'exit_code':0,'result':'PASS','evidence_path':f'docs/exec-plans/evidence/{roots['identity'].split('/')[-1]}/checks/{r['check_id']}.json','collection':nodes,'execution':nodes,'junit':nodes,'phases':{p:nodes for p in ['setup','call','teardown']},'skips':0,'errors':0,'deselections':0,'worker_loss':False,'bootstrap_reused':False})
    return rows

def fixture_premise(selected='HG-201',foreign='HG-202',body_salt=''):
    roots={k:hex(i)[2:]*40 for i,k in enumerate(['original','protected','original_selected','bootstrap','bootstrap_tree','tested','result','final','final_tree'],1)}
    roots.update(identity='harness-governance-v0.1/'+selected,controller='a'*64,authority='b'*64,policy='c'*64,image='d'*64)
    kb=fixture_bundle(roots,'K');hb=fixture_bundle(roots,'H');roots['controller']=kb['controller']
    body=('ordinary synthetic collection body'+body_salt+'\n').encode()*750;key=sh(body);bodies={};objects=[];object_bytes={}
    for owner,count in [(selected,2),(foreign,4)]:
        nf.put_representation(objects,bodies,object_bytes,f'docs/exec-plans/evidence/{owner}/retained',body,references=count)
    nf.put_plain(objects,object_bytes,'docs/exec-plans/evidence/HG-201/preimport-stage/scope.json',b'ordinary scope observation\n')
    objects.sort(key=lambda x:x['path']);retained_groups={key:fixture_group_binding(objects,key)};inv=fixture_inventory_oracle(objects,bodies,retained_groups,object_bytes)
    counts={'digest':inv['digest'],'files':inv['files'],'stored_bytes':inv['stored_bytes'],'maps':2,'edges':45}
    output=fixture_preimport_output(fixture_preimport_bindings(roots),counts,FixtureBudget(clock=lambda:0),{'paths':inv['preserved_paths'],'bytes':inv['preserved_bytes']})
    prechecks={id:0 for id in PHASE['stage_check_ids']}
    prechecks.update(positive_identities='COMPLETE_SAME_COLLECTION_EXECUTION_PHASE_JUNIT',skips=0,deselections=0,errors=0,bootstrap_reuse=False)
    public_roots={'identity':roots['identity'],'original':roots['original'],'tested':roots['tested'],'public_child_command':f'python tools/harness/compact_evidence.py audit --base {roots['original']} --head {roots['tested']} --identity {selected}'}
    report={'identity':selected,'base':roots['original'],'head':roots['tested'],'stored_bytes':inv['stored_bytes'],'files':inv['files'],'inventory_sha256':inv['digest'],'native_complete':True,'errors':inv['errors'],'remedy':'python tools/harness/compact_evidence.py capture --help'}
    child={'exit_code':1,'complete':True,'timeout':False,'interrupted':False,'command':public_roots['public_child_command'],'tested':roots['tested'],'stdout':json.dumps(report),'stderr':''}
    gates={i:'ACTUALLY_OBSERVED_PASS' for i in ['app_unit','app_harness','app_full_database','cleanup','live_hosted_required','selected_ci_pr','strict_worker_live']}
    facts={
    'RULE_MERGED':{'protected':roots['protected'],'normally_merged':True,'protected_scope_corrected':True,'baseline_complete_independent_install_review':True},
    'STAGE_REGRANT':{'explicit_root_grant':'STAGING_ONLY','paths':PHASE['staging_paths'],'db_app_reserved':False},
    'STAGE_FROZEN':{'K':roots['bootstrap'],'Q':roots['original_selected'],'tree':roots['bootstrap_tree'],'clean':True,'Q_first_parent':True,'P_imported':False,'changed_paths':['tools/harness/compact_evidence.py','tools/harness/local_gate.py','tests/harness/test_local_gate.py'],'immutable_originals_unchanged':True},
    'STAGE_CHECKS':prechecks,
    'BOOTSTRAP_REVIEW':{'K':roots['bootstrap'],'general':'PASS','security':'PASS','independent':True,'bundle':kb},
    'BOOTSTRAP_INSTALL':{'K':roots['bootstrap'],'bundle':kb,'outside_checkout':True,'root_installed':True,'imports_installed_only':True},
    'PREIMPORT':{'K':roots['bootstrap'],'P':roots['protected'],'controller':kb['controller'],'entry':'PRIVATE_ROOT_OPERATOR','config_private_regular':True,'app_authenticated':True,'existing_root_task_selection':roots['identity'],'lock_held':True,'owned_store':True,'original_declaration':roots['original_selected'],'output':output,'native_predicates':'ALL_NATIVE_O_TO_ACTUAL_K_OBSERVED','all_group_predicates':'MULTI_OWNER_V2_COMPLETE','snapshot_before':{'P':roots['protected'],'K':roots['bootstrap'],'controller':kb['controller']},'snapshot_after':{'P':roots['protected'],'K':roots['bootstrap'],'controller':kb['controller']}},
    'IMPORT_RECHECK':{'K':roots['bootstrap'],'P':roots['protected'],'controller':kb['controller'],'actual_operation_reobserved':True,'explicit_root_grant':'FINAL_AUTHOR_CONTINUATION'},
    'BASE_IMPORT':{'parents':[roots['bootstrap'],roots['protected']],'every_import_edge':'NATIVE_VERIFIED','maps_sources_unchanged':True,'original_declaration':roots['original_selected']},
    'STABLE_T':{'T':roots['tested'],'P_ancestor':True,'helpers_manifest_committed_before_T':True,'first_parent_Q_retained':True},
    'AUTHOR_CHECKS':{'T':roots['tested'],'rows':fixture_author_checks(roots),'public_denial':fixture_public_assertion(child,inv,public_roots)},
    'RESULT_R':{'R':roots['result'],'T':roots['tested'],'author_checks_only':True,'external_gates':'PENDING_EXTERNAL_OBSERVATION','no_external_NOT_RUN_selected_rows':True},
    'TASK_REVIEWS':{'R':roots['result'],'general':'PASS','security':'PASS','independent':True},
    'REVIEW_SUFFIX':{'R':roots['result'],'H':roots['final'],'linear_own_review_only':True,'post_R_task_evidence':False},
    'FINAL_INSTALL':{'H':roots['final'],'bundle':hb,'general':'PASS','security':'PASS','independent':True,'root_installed':True,'outside_checkout':True},
    'ADMISSION':{'P':roots['protected'],'H':roots['final'],'controller':hb['controller'],'exact_current_root_admission':True,'native_selected_identity':roots['identity']},
    'FINAL_ORIGINAL_AND_LIVE':{'P':roots['protected'],'H':roots['final'],'controller':hb['controller'],'private_O_to_H':'ALL_NATIVE_OBSERVED','complete_owner_set':sorted({x['path'].split('/')[3] for x in objects if x['kind']=='ENVELOPE'}),'original_inventory_digest':inv['digest'],'strict_P_to_H':'ALL_NATIVE_OBSERVED','accounted_output_published_after_live':True,'all_native_errors_propagated':True},
    'FINAL_PUBLIC_DENIAL':{'H':roots['final'],'enclosing_exit':0,'child_exit':1,'full_inventory_exact_derived_error_set':True,'root_outside_git':True},
    'WORKER_AND_HOSTED':{'P':roots['protected'],'H':roots['final'],'worker_args':['--ci-pr-base',roots['protected'],'--ci-pr-head',roots['final']],'private_credential_passed':False,'gates':gates},
    'FINAL_SNAPSHOT':{'P':roots['protected'],'H':roots['final'],'controller':hb['controller'],'snapshot_unchanged':True,'admission_unchanged':True,'installation_unchanged':True},
    'NORMAL_MERGE':{'P':roots['protected'],'H':roots['final'],'no_bypass':True,'all_hard_prerequisites_observed':True}}
    return {'synthetic_only':True,'roots':roots,'inventory_objects':objects,'bodies':bodies,'object_bytes':object_bytes,'retained_groups':retained_groups,'independent_facts':facts,'public_child':child,'public_roots':public_roots,'disposition':{'paths':inv['preserved_paths'],'bytes':inv['preserved_bytes']}}

def fixture_events(premise):return [{'phase':p,'actor':ROLES[p],'facts':copy.deepcopy(premise['independent_facts'][p])} for p in PHASE['ordered_phases']]

def evaluate_synthetic_sequence(events,premise):
    require(premise.get('synthetic_only') is True,'NOT_SYNTHETIC_PREMISE')
    structure(events)
    require(type(events) is list and len(events)<=64,'EVENT_LIMIT')
    require([e.get('phase') for e in events]==PHASE['ordered_phases'],'PHASE_ORDER_OR_COMPLETENESS')
    oracle=fixture_inventory_oracle(premise['inventory_objects'],premise['bodies'],premise['retained_groups'],premise['object_bytes'])
    fixture_public_assertion(premise['public_child'],oracle,premise['public_roots'])
    for e in events:
        require(set(e)=={'phase','actor','facts'},'UNKNOWN_EVENT_FIELD')
        require(e['actor']==ROLES[e['phase']],'PHASE_OWNERSHIP')
        exact(e['facts'],premise['independent_facts'][e['phase']])
        if e['phase']=='STAGE_FROZEN':require(all(fixture_scope(p) for p in e['facts']['changed_paths']),'STAGING_SCOPE')
        if e['phase']=='PREIMPORT':
            jsonschema.validate(e['facts']['output'],PRESCHEMA)
            require(e['facts']['output']['ready_for_exact_import'] is True,'NO_IMPORT_READINESS')
    return {'status':'DEFINITION_ROUTE_DEMONSTRATED','synthetic_only':True,'runtime_eligibility':'NOT_DETERMINED','native_actual_O_to_K':'NOT_RUN','installed_host':'NOT_RUN','acceptance_eligible':False,'execution_reuse':False,'phases':len(events)}


def fixture_multiphase_premise(foreign_count=2):
    'Explicit synthetic complete worlds. Actual current seven-owner data is separate.\n\n    K keeps the original two-owner inventory. T/H contain all synthetic foreign\n    owners after ordered P import. No filtering of the real P/Q observed group.\n    '
    require(type(foreign_count) is int and 2<=foreign_count<=7,'SYNTHETIC_OWNER_COUNT')
    p=fixture_premise();p['preimport_inventory_objects']=copy.deepcopy(p['inventory_objects']);p['preimport_retained_groups']=copy.deepcopy(p['retained_groups']);p['preimport_object_bytes']=copy.deepcopy(p['object_bytes'])
    key=next(iter(p['bodies']))
    for n in range(foreign_count-1):
        owner=f'HG-{203+n}'
        nf.put_representation(p['inventory_objects'],p['bodies'],p['object_bytes'],f'docs/exec-plans/evidence/{owner}/retained',bytes.fromhex(p['bodies'][key]),references=2)
    p['inventory_objects'].sort(key=lambda x:x['path']);p['retained_groups']={key:fixture_group_binding(p['inventory_objects'],key)};inv=fixture_inventory_oracle(p['inventory_objects'],p['bodies'],p['retained_groups'],p['object_bytes'])
    report=json.loads(p['public_child']['stdout']);report.update(stored_bytes=inv['stored_bytes'],files=inv['files'],inventory_sha256=inv['digest'],errors=inv['errors']);p['public_child']['stdout']=json.dumps(report)
    p['independent_facts']['AUTHOR_CHECKS']['public_denial']=fixture_public_assertion(p['public_child'],inv,p['public_roots'])
    p['independent_facts']['FINAL_ORIGINAL_AND_LIVE'].update(complete_owner_set=sorted({x['path'].split('/')[3] for x in p['inventory_objects'] if x['kind']=='ENVELOPE'}),original_inventory_digest=inv['digest'])
    return p
