"""Scratch definition study only. No installed context, runtime API or credential.

Fixtures are immutable-data observations or explicit synthetic perturbations.
They must never be accepted by the prospective installed host as an attestation.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import PurePosixPath

LIMITS = {
    'commits':4096, 'parent_edges':8192, 'path_entries':65536, 'paths':4096,
    'captures':512, 'groups':128, 'git_operations':16384, 'git_output_bytes':67108864,
    'decoded_bytes':268435456, 'comparison_bytes':268435456, 'json_depth':32,
    'json_nodes':65536, 'command_chars':4096, 'path_chars':1024, 'owner_chars':80,
    'timestamp_chars':80, 'list_entries':512, 'output_bytes':1048576,
    'blob_cache_objects':1024, 'blob_cache_bytes':16777216,
    'proof_cache_groups':128, 'proof_cache_bytes':1048576,
}
DEADLINE_NS = 120000000000


class Denial(ValueError):
    pass


def exact(value, pattern):
    return isinstance(value, str) and re.fullmatch(pattern, value) is not None


def path(value):
    return (isinstance(value, str) and 0 < len(value) <= 1024
            and not value.startswith('/') and '\\' not in value and '\0' not in value
            and all(s not in ('', '.', '..') for s in value.split('/')))


def identity(value):
    return exact(value, r'(?:harness-governance-v0\.1/HG-[0-9]{3}|harness-backlog-v0\.2/KL-[0-9]{3}[A-Z]?)')


def owner(value):
    if not path(value):
        raise Denial('INVALID_PATH')
    match = re.fullmatch(r'docs/exec-plans/(?:evidence|reviews)/((?:HG|KL)-[0-9]{3}[A-Z]?)/.+', value)
    if match is None:
        raise Denial('INVALID_OWNER')
    return match[1]


def shape(value, fields):
    if type(value) is not dict or set(value) != set(fields):
        raise Denial('INVALID_SHAPE')


def object_binding(value):
    shape(value, ('path', 'mode', 'blob', 'bytes', 'sha256'))
    if (not path(value['path']) or value['mode'] not in ('100644', '100755')
            or not exact(value['blob'], r'[0-9a-f]{40}')
            or not exact(value['sha256'], r'[0-9a-f]{64}')
            or type(value['bytes']) is not int or not 0 <= value['bytes'] <= 8388608):
        raise Denial('INVALID_OBJECT')


def bounded_structure(value, *, node_limit=65536, list_limit=512, depth_limit=32):
    """Reserve pending work before allocating child lists; bools are scalar values."""
    pending = [(value, 0)]
    processed = peak = 0
    while pending:
        current, depth = pending.pop()
        processed += 1
        if processed > node_limit or depth > depth_limit:
            raise Denial('LIMIT_EXHAUSTED')
        children = (len(current) * 2 if type(current) is dict else
                    len(current) if type(current) is list else 0)
        if type(current) is list and len(current) > list_limit:
            raise Denial('LIMIT_EXHAUSTED')
        if processed + len(pending) + children > node_limit:
            raise Denial('LIMIT_EXHAUSTED')
        if type(current) is dict:
            for k, v in current.items():
                pending.extend(((k, depth + 1), (v, depth + 1)))
        elif type(current) is list:
            pending.extend((v, depth + 1) for v in current)
        peak = max(peak, len(pending))
    return {'nodes': processed, 'peak_pending': peak}


class Budget:
    def __init__(self, limits, *, now=time.monotonic_ns):
        if (type(limits) is not dict or any(k not in LIMITS or type(v) is not int or not 0<=v<=LIMITS[k]
                                           for k,v in limits.items())):
            raise Denial('LIMIT_EXHAUSTED')
        self.limits = dict(limits)
        self.used = {k: 0 for k in limits}
        self.now = now
        self.start = now()
        self.exhausted = False

    def check(self):
        """Reinspect actual counters and clock, even after the last predicate."""
        if self.now() - self.start > DEADLINE_NS:
            self.exhausted = True
            raise Denial('DEADLINE_EXCEEDED')
        if (self.exhausted or any(name not in LIMITS or name not in self.limits or type(value) is not int or value < 0
                                 or value > self.limits[name] or value > LIMITS[name]
                                 for name,value in self.used.items())):
            self.exhausted = True
            raise Denial('LIMIT_EXHAUSTED')

    def charge(self, name, amount):
        if self.exhausted or name not in self.limits or type(amount) is not int or amount < 0:
            self.exhausted = True
            raise Denial('LIMIT_EXHAUSTED')
        self.check()
        prospective = self.used[name] + amount
        # Preserve an attempted observed charge, including a rejected overrun.
        self.used[name] = prospective
        if prospective > self.limits[name]:
            self.exhausted = True
            raise Denial('LIMIT_EXHAUSTED')


def reachable(start, children):
    pending=[start];seen=set()
    while pending:
        node=pending.pop()
        if node in seen:continue
        seen.add(node)
        pending.extend(n for n in children.get(node,()) if n not in seen)
    return seen


def check_edge_history(states, introduction, *, endpoints):
    """The first absent->original addition is allowed; all later mutations deny.

    `states` is a closed observation graph from exact Git, not a trusted receipt.
    Incoming boundaries are explicitly present, never omitted as a cutoff.
    """
    shape(states, ('path', 'original', 'nodes', 'edges', 'imports', 'parents', 'boundaries'))
    object_binding(states['original'])
    if states['path'] != states['original']['path']:
        raise Denial('OBJECT_MISMATCH')
    if not exact(introduction, r'[0-9a-f]{40}'):
        raise Denial('INVALID_REVISION')
    nodes = states['nodes']
    if type(nodes) is not dict or introduction not in nodes:
        raise Denial('INCOMPLETE_HISTORY')
    expected = states['original']
    parents_by_child = states['parents']
    if (type(parents_by_child) is not dict or type(states['boundaries']) is not list
            or set(states['boundaries']) != set(nodes)-set(parents_by_child)
            or len(states['boundaries']) != len(set(states['boundaries']))):
        raise Denial('INCOMPLETE_HISTORY')
    complete_edges = set()
    for child, parents in parents_by_child.items():
        if (child not in nodes or type(parents) is not list or not parents
                or len(parents)!=len(set(parents)) or any(p not in nodes for p in parents)):
            raise Denial('INCOMPLETE_HISTORY')
        complete_edges.update((p,child) for p in parents)
    if complete_edges != {tuple(e) for e in states['edges']}:
        raise Denial('INCOMPLETE_HISTORY')
    if (not endpoints or any(not exact(e,r'[0-9a-f]{40}') or e not in parents_by_child for e in endpoints)
            or introduction not in parents_by_child):
        raise Denial('INCOMPLETE_HISTORY')
    children={n:set() for n in nodes}
    indegree={n:0 for n in nodes}
    for parent,child in complete_edges:
        children[parent].add(child);indegree[child]+=1
    ready=[n for n,d in indegree.items() if d==0];visited=set()
    while ready:
        n=ready.pop();visited.add(n)
        for child in children[n]:
            indegree[child]-=1
            if indegree[child]==0:ready.append(child)
    if len(visited)!=len(nodes):raise Denial('HISTORY_CYCLE')
    forward=reachable(introduction,children)
    ancestors=set()
    for end in endpoints:ancestors.update(reachable(end,parents_by_child))
    if (not set(parents_by_child)<=forward or not set(nodes)<=ancestors
            or any(not children[b] or nodes[b] is not None for b in states['boundaries'])):
        raise Denial('HISTORY_DISCONNECTED')
    imports = states['imports']
    if type(imports) is not dict:
        raise Denial('INVALID_IMPORT')
    for child, parents in imports.items():
        if (type(parents) is not list or len(parents) != 2 or parents[0] == parents[1]
                or child not in nodes or nodes[child] != expected
                or any(p not in nodes for p in parents)
                or nodes[parents[0]] is not None or nodes[parents[1]] != expected
                or parents_by_child.get(child) != parents
                or any([p,child] not in states['edges'] for p in parents)):
            raise Denial('INVALID_IMPORT')
    for rev, value in nodes.items():
        if not exact(rev, r'[0-9a-f]{40}') or (value is not None and value != expected):
            raise Denial('HISTORY_CHANGED')
    seen = set()
    for edge in states['edges']:
        if type(edge) is not list or len(edge) != 2 or tuple(edge) in seen:
            raise Denial('INVALID_EDGE')
        seen.add(tuple(edge))
        parent, child = edge
        if parent not in nodes or child not in nodes:
            raise Denial('INCOMPLETE_HISTORY')
        before, after = nodes[parent], nodes[child]
        if before != after and not (before is None and after == expected and
                                   (child == introduction or child in imports)):
            raise Denial('HISTORY_CHANGED')
    incoming = [p for p, c in states['edges'] if c == introduction]
    if not incoming or any(nodes[p] is not None for p in incoming) or nodes[introduction] != expected:
        raise Denial('INTRODUCTION_NOT_PROVED')


def custody_predicate(proof, *, original_sources):
    """Checks bounded observation structure. No authority or native audit inferred."""
    bounded_structure(proof)
    shape(proof, ('selected_identity', 'original_base', 'protected_base', 'original_selected',
                  'members', 'physical_paths', 'inventory_intersection', 'delivery', 'map_binding'))
    if not identity(proof['selected_identity']):
        raise Denial('INVALID_IDENTITY')
    selected = proof['selected_identity'].split('/')[-1]
    for field in ('original_base', 'protected_base', 'original_selected'):
        if not exact(proof[field], r'[0-9a-f]{40}'):
            raise Denial('INVALID_REVISION')
    members = proof['members']
    if type(members) is not list or not 2 <= len(members) <= 512:
        raise Denial('GROUP_INCOMPLETE')
    paths = proof['physical_paths']
    if type(paths) is not list or not paths:
        raise Denial('GROUP_INCOMPLETE')
    by_path = {}
    for obj in paths:
        object_binding(obj)
        if obj['path'] in by_path:
            raise Denial('DUPLICATE_PHYSICAL_PATH')
        by_path[obj['path']] = obj
    if len(by_path) > 4096 or sum(x['bytes'] for x in paths) > 16777216:
        raise Denial('LIMIT_EXHAUSTED')
    if proof['inventory_intersection'] != sorted(by_path):
        raise Denial('INVENTORY_MISMATCH')
    seen, payloads, owners, raws = set(), {}, set(), set()
    declaration_objects={};commit_parents={};physical_histories={}
    for member in members:
        shape(member, ('envelope', 'payload', 'raw_sha256', 'raw_bytes', 'declaration',
                       'introduction', 'history', 'payload_introduction', 'payload_history',
                       'protected_state', 'representation'))
        e, p = member['envelope'], member['payload']
        object_binding(e)
        object_binding(p)
        o = owner(e['path'])
        owners.add(o)
        if e['path'] in seen or e['bytes'] > 262144:
            raise Denial('INVALID_ENVELOPE_MEMBERSHIP')
        seen.add(e['path'])
        if by_path.get(e['path']) != e or by_path.get(p['path']) != p:
            raise Denial('OBJECT_MISMATCH')
        if owner(p['path']) != o or PurePosixPath(e['path']).parent != PurePosixPath(p['path']).parent:
            raise Denial('PAYLOAD_OWNER_OR_DIRECTORY')
        if o in payloads and payloads[o] != p['path']:
            raise Denial('MULTIPLE_OWNER_PAYLOADS')
        payloads[o] = p['path']
        if (not exact(member['raw_sha256'], r'[0-9a-f]{64}')
                or type(member['raw_bytes']) is not int or not 16384 <= member['raw_bytes'] <= 67108864):
            raise Denial('INVALID_RAW_IDENTITY')
        raws.add((member['raw_sha256'], member['raw_bytes']))
        shape(member['representation'], ('codec', 'raw_sha256', 'raw_bytes', 'stored_sha256', 'stored_bytes',
                                         'raw_bytes_equal', 'native_read_observation'))
        rep = member['representation']
        if (rep['codec'] not in ('gzip-v1', 'xz-v1')
                or (rep['raw_sha256'], rep['raw_bytes']) != (member['raw_sha256'], member['raw_bytes'])
                or (rep['stored_sha256'], rep['stored_bytes']) != (p['sha256'], p['bytes'])
                or rep['raw_bytes_equal'] != 'OBSERVED_EXACT_BYTES'
                or rep['native_read_observation'] != 'OBSERVED_NATIVE_CODEC_AND_CLASSIFIER_RETURNED_ORDINARY'
                or PurePosixPath(p['path']).name != member['raw_sha256'] + ('.gz' if rep['codec']=='gzip-v1' else '.xz')):
            raise Denial('REPRESENTATION_INVALID')
        # This tag is an author observation, explicitly not a host credential.
        declaration = member['declaration']
        shape(declaration, ('identity', 'revision', 'object', 'pointers', 'ref', 'authority_chain'))
        if (not identity(declaration['identity']) or declaration['identity'].split('/')[-1] != o
                or not exact(declaration['revision'], r'[0-9a-f]{40}')
                or declaration['ref'] != e['path'] or not declaration['pointers']
                or declaration['authority_chain'] not in ('PROTECTED_PACKET_FROZEN_ORIGINAL', 'NORMAL_FOREIGN_DELIVERY_ORIGINAL')):
            raise Denial('DECLARATION_INVALID')
        object_binding(declaration['object'])
        expected_stem = ('docs/exec-plans/governance/'+o if o.startswith('HG-')
                         else 'docs/exec-plans/completed/'+o+'_RESULT')
        if declaration['object']['path'] not in (expected_stem+'.yaml',expected_stem+'.json'):
            raise Denial('DECLARATION_INVALID')
        if any(not exact(x, r'(?:files_changed/[0-9]+|evidence_refs/[0-9]+|checks_run/[0-9]+/evidence_ref)') for x in declaration['pointers']):
            raise Denial('DECLARATION_INVALID')
        key=(declaration['revision'],declaration['object']['path'])
        if key in declaration_objects and declaration_objects[key]!=declaration['object']:
            raise Denial('CONTRADICTORY_PROVENANCE')
        declaration_objects[key]=declaration['object']
        verify_original_membership(declaration,original_sources)
        if o == selected:
            if (declaration['revision'] != proof['original_selected']
                    or declaration['authority_chain'] != 'PROTECTED_PACKET_FROZEN_ORIGINAL'
                    or member['protected_state'] != 'ABSENT'):
                raise Denial('SELECTED_CUSTODY_INVALID')
        elif declaration['authority_chain'] != 'NORMAL_FOREIGN_DELIVERY_ORIGINAL' or member['protected_state'] != 'EXACT_ORIGINAL':
            raise Denial('FOREIGN_CUSTODY_INVALID')
        endpoints=([proof['original_selected']] if o==selected else
                   [proof['protected_base'],proof['original_selected']])
        for history,introduction,binding in [(member['history'],member['introduction'],e),
                                            (member['payload_history'],member['payload_introduction'],p)]:
            if history['path']!=binding['path'] or history['original']!=binding:
                raise Denial('OBJECT_MISMATCH')
            if binding['path'] in physical_histories and physical_histories[binding['path']]!=(history,introduction):
                raise Denial('CONTRADICTORY_PROVENANCE')
            physical_histories[binding['path']]=(history,introduction)
            check_edge_history(history,introduction,endpoints=endpoints)
            for rev,parents in history['parents'].items():
                if rev in commit_parents and commit_parents[rev]!=parents:
                    raise Denial('CONTRADICTORY_PROVENANCE')
                commit_parents[rev]=parents
    if len(owners) != 2 or selected not in owners or len(raws) != 1:
        raise Denial('GROUP_OWNER_OR_RAW')
    if set(by_path) != seen | set(payloads.values()):
        raise Denial('GROUP_INCOMPLETE')
    delivery = proof['delivery']
    shape(delivery, ('commit', 'parents', 'original_record', 'foreign_owner', 'relation_observations'))
    if (len(delivery['parents']) != 2 or delivery['parents'][0] == delivery['parents'][1]
            or any(not exact(v, r'[0-9a-f]{40}') for v in [delivery['commit'], delivery['original_record'], *delivery['parents']])
            or delivery['foreign_owner'] != next(o for o in owners if o != selected)
            or delivery['relation_observations'] != ['ORIGINAL_RECORD_TO_PR_HEAD', 'DELIVERY_TO_PROTECTED', 'DELIVERY_TO_SELECTED', 'CORRECT_PARENT_ORIENTATION']):
        raise Denial('DELIVERY_INVALID')
    for member in members:
        if owner(member['envelope']['path']) != selected and member['declaration']['revision'] != delivery['original_record']:
            raise Denial('FOREIGN_CUSTODY_INVALID')
        if owner(member['envelope']['path'])==selected:continue
        original_record=load_source_record(original_sources[(member['declaration']['revision'],member['declaration']['object']['path'])]['content'])
        if original_record['base_commit']!=delivery['parents'][0]:raise Denial('CONTRADICTORY_PROVENANCE')
        for history in [member['history'],member['payload_history']]:
            d=delivery['commit'];b,j=delivery['parents'];f=delivery['original_record']
            if history['imports'].get(d)!=[b,j] or history['parents'].get(d)!=[b,j]:
                raise Denial('DELIVERY_INVALID')
            for endpoint in [f,j,d,proof['protected_base'],proof['original_selected']]:
                if history['nodes'].get(endpoint)!=history['original']:
                    raise Denial('DELIVERY_INVALID')
            if f not in reachable(j,history['parents']):raise Denial('DELIVERY_INVALID')
            for end in [proof['protected_base'],proof['original_selected']]:
                if d not in reachable(end,history['parents']):raise Denial('DELIVERY_INVALID')
            for child,parents in history['imports'].items():
                if child!=d and d not in reachable(parents[1],history['parents']):
                    raise Denial('DELIVERY_INVALID')
    mapping = proof['map_binding']
    shape(mapping, ('object', 'identity', 'original_base', 'source', 'admission', 'member_relationship', 'native_full_audit'))
    object_binding(mapping['object'])
    if (mapping['identity'] != selected or mapping['original_base'] != proof['original_base']
            or any(not exact(mapping[v], r'[0-9a-f]{40}') for v in ('source','admission'))
            or mapping['member_relationship'] != 'UNCHANGED_UNMAPPED_ORDINARY_REPRESENTATION'
            or mapping['native_full_audit'] != 'NOT_RUN'):
        raise Denial('MAP_CONTEXT_INVALID')
    original_map=verify_source_object((proof['original_selected'],mapping['object']['path']),original_sources)
    admitted_map=verify_source_object((mapping['admission'],mapping['object']['path']),original_sources)
    if original_map['object']!=mapping['object'] or admitted_map['content']!=original_map['content']:
        raise Denial('MAP_CONTEXT_INVALID')
    map_record=load_source_record(original_map['content'])
    if (map_record.get('compact_reencoding')!='v1' or map_record.get('identity')!=mapping['identity']
            or map_record.get('protected_base')!=mapping['original_base']
            or map_record.get('source_revision')!=mapping['source']):
        raise Denial('MAP_CONTEXT_INVALID')
    return {'status': 'CUSTODY_PREDICATE_DEMONSTRATED', 'representations': len(members),
            'physical_paths': len(by_path), 'physical_bytes': sum(x['bytes'] for x in paths),
            'execution_attribution': 'UNVERIFIED', 'acceptance_eligible': False, 'execution_reuse': False,
            'native_full_audit': 'NOT_RUN', 'runtime_eligibility': 'NOT_DETERMINED'}


def atomic_study(proofs, budget, *, original_sources):
    """No result from one group survives an incomplete/exhausted invocation."""
    results = []
    incomplete = False
    reasons = []
    seen_paths = set()
    roots = None
    for proof in proofs:
        try:
            budget.charge('groups', 1)
            current_roots = tuple(proof[k] for k in ('selected_identity','original_base','protected_base','original_selected'))
            if roots is not None and current_roots != roots:
                raise Denial('INCOMPLETE_CONTEXT')
            roots = current_roots
            current_paths = {p['path'] for p in proof['physical_paths']}
            if seen_paths.intersection(current_paths):
                raise Denial('INVENTORY_MISMATCH')
            seen_paths.update(current_paths)
            results.append(custody_predicate(proof,original_sources=original_sources))
            budget.check()
        except Denial as ex:
            reasons.append(str(ex))
            incomplete |= str(ex) in ('LIMIT_EXHAUSTED','DEADLINE_EXCEEDED','INCOMPLETE_CONTEXT','INCOMPLETE_HISTORY',
                                      'GROUP_INCOMPLETE','DECLARATION_SOURCE_UNAVAILABLE')
        try:budget.check()
        except Denial as ex:
            if str(ex) not in reasons:reasons.append(str(ex))
            incomplete=True
    # Publication preflight is mandatory for success and ordinary denial alike.
    try:budget.check()
    except Denial as ex:
        if str(ex) not in reasons:reasons.append(str(ex))
        incomplete=True
    observed={'elapsed_ns':budget.now()-budget.start,'consumed':dict(budget.used)}
    # Check the newly observed final clock, not just a stale previous check.
    if observed['elapsed_ns']>DEADLINE_NS:
        if 'DEADLINE_EXCEEDED' not in reasons:reasons.append('DEADLINE_EXCEEDED')
        incomplete=True
    if any(k not in LIMITS or k not in budget.limits or type(v) is not int or v<0 or v>LIMITS[k] or v>budget.limits[k]
           for k,v in observed['consumed'].items()):
        if 'LIMIT_EXHAUSTED' not in reasons:reasons.append('LIMIT_EXHAUSTED')
        incomplete=True
    if reasons:
        return {'complete': not incomplete, 'accounted_paths': 0, 'accounted_bytes': 0,
                'groups': ['CUSTODY_DENIED'] * len(proofs), 'reasons': reasons,**observed}
    return {'complete': True, 'accounted_paths': 0, 'accounted_bytes': 0,
            'groups': [x['status'] for x in results], 'reasons': [],**observed}


def cache_key(context, obj, purpose):
    # A key describes isolation only; possession grants no private authority.
    shape(context, ('repository','object_format','installed_release','controller_assets_sha256',
                    'authority_sha256','selected_identity','original_base','protected_base','original_selected',
                    'head','packet_blob','map_blob','source','admission','declaration_blob','delivery',
                    'group_sha256','edges_sha256','invocation'))
    if (not exact(context['repository'],r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+')
            or context['object_format'] != 'sha1' or not identity(context['selected_identity'])):
        raise Denial('INCOMPLETE_CONTEXT')
    for key in ('installed_release','original_base','protected_base','original_selected','head',
                'packet_blob','map_blob','source','admission','declaration_blob','delivery'):
        if not exact(context[key],r'[0-9a-f]{40}'):
            raise Denial('INCOMPLETE_CONTEXT')
    for key in ('controller_assets_sha256','authority_sha256','group_sha256','edges_sha256'):
        if not exact(context[key],r'[0-9a-f]{64}'):
            raise Denial('INCOMPLETE_CONTEXT')
    if purpose != 'ORIGINAL_CUSTODY' or not exact(context['invocation'], r'[\x21-\x7e]{1,128}'):
        raise Denial('CALLER_OR_INVOCATION_INVALID')
    object_binding(obj)
    return hashlib.sha256(json.dumps([context, obj, purpose],sort_keys=True).encode()).hexdigest()


def validate_output(value, schema):
    """Schema plus actual physical accounting; diagnostic output is no credential."""
    import jsonschema
    jsonschema.validate(value,schema)
    exhausted=[k for k,v in value['consumed'].items() if v>LIMITS[k]]
    timed_out=value['elapsed_ns']>DEADLINE_NS
    if exhausted or timed_out:
        required=set(['LIMIT_EXHAUSTED'] if exhausted else [])|set(['DEADLINE_EXCEEDED'] if timed_out else [])
        if (value['complete'] or value['status']!='CUSTODY_DENIED'
                or value['accounted_paths'] or value['accounted_bytes']
                or not required<=set(value['denial_reasons'])):
            raise Denial('LIMIT_EXHAUSTED' if exhausted else 'DEADLINE_EXCEEDED')
    seen=set()
    for obj in value['physical_paths']:
        object_binding(obj)
        if obj['path'] in seen:
            raise Denial('DUPLICATE_PHYSICAL_PATH')
        seen.add(obj['path'])
    if value['status']=='CUSTODY_ACCOUNTED_ORIGINAL_INVENTORY':
        if (value['accounted_paths']!=len(seen)
                or value['accounted_bytes']!=sum(p['bytes'] for p in value['physical_paths'])
                or value['elapsed_ns']>DEADLINE_NS):
            raise Denial('INVENTORY_MISMATCH')


def native_authority_structure(value):
    """Native authority schema lists retain native limits; proof lists keep 512.

    Full original-record source parsing is bounded by source bytes/tokens/nodes/
    depth and its exact original native schema. This is not an execution partition
    or a projected custody proof list. No original membership list is truncated.
    """
    pending=[(value,0)];processed=0
    while pending:
        current,depth=pending.pop();processed+=1
        if processed>65536 or depth>32:raise Denial('LIMIT_EXHAUSTED')
        count=len(current)*2 if type(current) is dict else len(current) if type(current) is list else 0
        if processed+len(pending)+count>65536:raise Denial('LIMIT_EXHAUSTED')
        if type(current) is dict:
            for k,v in current.items():pending.extend(((k,depth+1),(v,depth+1)))
        elif type(current) is list:pending.extend((v,depth+1) for v in current)


def load_source_record(data):
    import yaml
    if type(data) is not bytes or len(data)>262144:raise Denial('DECLARATION_SOURCE_INVALID')
    class StrictLoader(yaml.SafeLoader):pass
    def unique_mapping(loader,node,deep=False):
        out={}
        for k,v in node.value:
            name=loader.construct_object(k,deep=deep)
            if name in out:raise Denial('DECLARATION_SOURCE_INVALID')
            out[name]=loader.construct_object(v,deep=deep)
        return out
    StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,unique_mapping)
    try:
        tokens=0
        for token in yaml.scan(data):
            tokens+=1
            if tokens>65536 or isinstance(token,(yaml.AliasToken,yaml.AnchorToken)):
                raise Denial('DECLARATION_SOURCE_INVALID')
        record=yaml.load(data,Loader=StrictLoader)
        native_authority_structure(record)
        return record
    except (yaml.YAMLError,TypeError,UnicodeError,RecursionError) as ex:
        raise Denial('DECLARATION_SOURCE_INVALID') from ex


def verify_source_object(key,sources):
    source=sources.get(key)
    if source is None:raise Denial('DECLARATION_SOURCE_UNAVAILABLE')
    shape(source,('object','content'));object_binding(source['object']);data=source['content']
    if (type(data) is not bytes or len(data)>262144 or len(data)!=source['object']['bytes']
            or source['object']['path']!=key[1]
            or hashlib.sha256(data).hexdigest()!=source['object']['sha256']
            or hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()!=source['object']['blob']):
        raise Denial('DECLARATION_SOURCE_INVALID')
    return source


def verify_original_membership(declaration, sources):
    """Independently supplied original bytes, never declaration flags as authority.

    Model source fixtures are non-authoritative; the installed host must read its
    own exact original Git objects after protected authority derivation.
    """
    import jsonschema
    key=(declaration['revision'],declaration['object']['path'])
    source=verify_source_object(key,sources)
    schema_source=verify_source_object((declaration['revision'],'HARNESS_CHANGE.schema.json' if
                               declaration['identity'].startswith('harness-governance-v0.1/') else 'THREAD_RESULT.schema.json'),sources)
    if source['object']!=declaration['object']:raise Denial('CONTRADICTORY_PROVENANCE')
    try:
        record=load_source_record(source['content'])
        schema=json.loads(schema_source['content'])
        jsonschema.validate(record,schema)
    except (json.JSONDecodeError,jsonschema.ValidationError) as ex:
        raise Denial('DECLARATION_SOURCE_INVALID') from ex
    identity_field='change_identity' if declaration['identity'].startswith('harness-governance-v0.1/') else 'task_identity'
    if record.get(identity_field)!=declaration['identity'] or len(declaration['pointers'])!=len(set(declaration['pointers'])):
        raise Denial('DECLARATION_INVALID')
    for pointer in declaration['pointers']:
        parts=pointer.split('/')
        try:
            values=record[parts[0]];ordinal=int(parts[1])
            if type(values) is not list or ordinal>=len(values):raise Denial('DECLARATION_INVALID')
            ref=values[ordinal] if len(parts)==2 else values[ordinal][parts[2]]
        except (KeyError,IndexError,ValueError,TypeError) as ex:raise Denial('DECLARATION_INVALID') from ex
        if ref!=declaration['ref']:raise Denial('DECLARATION_INVALID')
