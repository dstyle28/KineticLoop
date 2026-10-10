"""HG062 definition/fixture oracle only. Never imported by production callers.

Synthetic contexts model prerequisites; they do not authenticate real execution or
replace native guards. Immutable research verifies original documentary bindings,
never imports/evaluates historical source and never scans codec companions.
"""
import argparse
import ast
import copy
import hashlib
import json
import math
import re
import shlex
import subprocess
from pathlib import Path

import jsonschema
import yaml
from referencing import Registry

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
BASE = '4e9c60a242d84b81b6e82b635da6c7227af68912'
OBS = {'documentary_validation': 'BOUND_ORIGINAL_CLAIM',
       'semantic_validation': 'UNVERIFIED_ORIGINAL_COMPUTATION',
       'historical_execution': 'UNVERIFIED_MISSING_PRODUCER_EXIT',
       'historical_review_acceptance': 'NOT_CERTIFIED', 'acceptance_eligible': False}
LIMITS = {'blobs': 32, 'metadata_entries': 512, 'raw_bytes': 32 * 1024**2,
          'validator_bytes': 4 * 1024**2, 'other_bytes': 1024**2,
          'diff_paths': 4096, 'diff_bytes': 1024**2, 'tree_bytes': 1024**2,
          'git_operations': 64, 'nodes': 262144, 'depth': 64, 'ast_depth': 256,
          'classifier_bytes': 256 * 1024, 'classifier_work': 1024,
          'classifier_aggregate': 1024**2}
AUTH_PATHS = ['HARNESS_CHANGE.schema.json', 'THREAD_REVIEW.schema.json',
              'docs/harness/HARNESS_GOVERNANCE_CONTRACT.md',
              'docs/harness/THREAD_REVIEW_CONTRACT.md']


def require(value, reason):
    if not value:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, timeout=30)


def canonical(path):
    require(isinstance(path, str) and path and not any(c in path for c in '\x00\r\n\\'), 'path bytes')
    require(not path.startswith('/') and all(x not in ('', '.', '..') for x in path.split('/')), 'path canonical')
    return path


def inert(text):
    require(isinstance(text, str) and text and not any(c in text for c in '\x00\r\n'), 'inert attribution')


def hexstr(value, n):
    require(isinstance(value, str) and re.fullmatch('[0-9a-f]{' + str(n) + '}', value), 'full hexadecimal identity')


def strict(raw):
    require(len(raw) <= LIMITS['other_bytes'] and not raw.startswith(b'\xef\xbb\xbf'), 'JSON bytes')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    def nonfinite(value):
        raise ValueError('nonfinite JSON ' + value)
    value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=nonfinite)
    stack, count = [(value, 1)], 0
    while stack:
        item, depth = stack.pop()
        count += 1
        require(count <= LIMITS['nodes'] and depth <= LIMITS['depth'], 'parser bounds')
        if isinstance(item, dict):
            stack.extend((x, depth + 1) for kv in item.items() for x in kv)
        elif isinstance(item, list):
            stack.extend((x, depth + 1) for x in item)
        elif isinstance(item, float):
            require(math.isfinite(item), 'nonfinite parsed float')
    return value


def grammar(value, schema):
    jsonschema.Draft202012Validator(schema, registry=Registry()).validate(value)
    # JSON Schema treats 1.0 as integral; the closed definition requires integer tokens.
    def tokens(x, s):
        if 'anyOf' in s:
            matches = [q for q in s['anyOf'] if jsonschema.Draft202012Validator(q).is_valid(x)]
            require(matches, 'grammar union')
            tokens(x, matches[0])
        if s.get('type') == 'integer':
            require(type(x) is int, 'integer scalar token')
        if isinstance(x, dict):
            for key, item in x.items():
                if key in s.get('properties', {}):
                    tokens(item, s['properties'][key])
        if isinstance(x, list) and 'items' in s:
            for item in x:
                tokens(item, s['items'])
    tokens(value, schema)


def regular(entry):
    require(entry[0] in ('100644', '100755') and entry[1] == 'blob', 'regular object')
    hexstr(entry[2], 40)


def unique(items):
    require(len(items) == len(set(items)), 'duplicate identity')


def tuple_for(c):
    return (c['owner'], c['check_id'], c['B'], c['T'], c['command'], c['report_ref'])


# In this offline model only, Native is an internally issued fixture observation.
# This is not a production authentication mechanism or a caller-provided flag.
TOKEN = object()
class Native:
    def __init__(self, binding, state, exit_code, token):
        require(token is TOKEN, 'fixture native issuer')
        self.binding, self.state, self.exit_code = binding, state, exit_code


def classify(raw, c, catalog):
    require(c['purpose'] == 'GLOBAL_ARCHIVAL_GOVERNANCE_INVENTORY', 'caller purpose')
    require(not {c['owner'], c['D']}.intersection(c['selected_aliases']), 'selected owner alias')
    require(c['cache_kind'] == 'DOCUMENTARY_ONLY' and c['profile_version'] == catalog['draft_version'], 'profile/cache isolation')
    require(c['native_complete'] is True, 'unfinished native inventory')
    require(c['decoder'] == 'NATIVE_ALLOWED', 'native decoder denial')
    require(c['selection_basis'] == 'ORIGINAL_LINKAGE', 'selection from label/sample')
    for key, bound in LIMITS.items():
        require(type(c['usage'][key]) is int and 0 <= c['usage'][key] <= bound, 'budget ' + key)
    for key in ('B', 'T', 'R', 'M', 'validation_revision', 'protected_base', 'tree'):
        hexstr(c[key], 40)
    require(c['M'] in c['protected_first_parent'] and len(c['merge_candidates']) == 1 and c['merge_candidates'][0] == c['M'], 'original merge')
    for a, b in zip(('B', 'T', 'R', 'M'), ('T', 'R', 'M', 'protected_base')):
        require((c[a], c[b]) in c['ancestry'], 'lineage')
    require(c['owner'] == 'harness-governance-v0.1/' + c['D'], 'namespaced owner')
    for entry in c['entries'].values():
        regular(entry)
    require(c['record_ref'] == 'docs/exec-plans/governance/' + c['D'] + '.yaml', 'canonical record')
    require(c['review_ref'] == 'docs/exec-plans/reviews/' + c['D'] + '/GENERAL.json', 'canonical GENERAL')
    canonical(c['report_ref'])
    require(c['report_ref'].startswith('docs/exec-plans/evidence/' + c['D'] + '/'), 'owner evidence')
    for p in (c['record_ref'], c['report_ref'], c['review_ref']):
        require(p in c['entries'], 'original object absent')
    require(c['record_versions']['R'] == c['record_versions']['M'] == c['record_versions']['current'], 'record immutable')
    require(sha(raw) == c['report_hash_M'], 'report immutable')
    require(c['report_hash_current'] == c['report_hash_M'], 'current report immutable')
    require(len(c['reviews']) == 1, 'unique original GENERAL')
    review = c['reviews'][0]
    require(review['task_identity'] == c['owner'] and review['reviewed_head_sha'] == c['R'] and review['review_type'] == 'GENERAL', 'review identity')
    refs = review['evidence_refs']
    require(c['report_ref'] in refs or c['record_ref'] in refs, 'direct or one record hop')
    checks = [q for q in c['checks'] if q['evidence_ref'] == c['report_ref']]
    require(len(checks) == 1 and checks[0]['check_id'] == c['check_id'] and checks[0]['command'] == c['command'], 'unique exact original check')
    require(c['record_owner'] == c['owner'] and c['record_B'] == c['B'] and c['record_T'] == c['T'], 'record owner/B/T')
    inert(c['command']); require(shlex.split(c['command']), 'command argv')
    for path in AUTH_PATHS:
        entries = [e for e in c['authority'] if e['path'] == path]
        require(len(entries) == 1, 'original indexed authority uniqueness')
        e = entries[0]
        require(e['T_hash'] == e['R_hash'] == e['T_index_hash'] == e['R_index_hash'], 'original indexed authority bytes')
    report = strict(raw)
    require(c['form'] in catalog['profiles'], 'unknown form')
    grammar(report, catalog['profiles'][c['form']]['schema'])
    matches = [n for n, v in catalog['profiles'].items() if jsonschema.Draft202012Validator(v['schema']).is_valid(report)]
    require(matches == [c['form']], 'unambiguous closed grammar')
    semantic_fields(report, c, catalog)
    parent = []
    for observation in c['observations']:
        require(type(observation) is Native, 'unauthenticated native observation')
        if observation.binding == tuple_for(c):
            parent.append(observation)
    for observation in parent:
        require(observation.state == 'COMPLETED' and type(observation.exit_code) is int and observation.exit_code == 0, 'parent contradiction')
    if parent:
        return 'ORDINARY_NATIVE_EXIT_BINDING_ONLY'
    return dict(OBS)


def semantic_fields(r, c, catalog):
    form = c['form']
    def ref(path):
        canonical(path)
        require(path.startswith('docs/exec-plans/evidence/' + c['D'] + '/') and path in c['entries'], 'secondary reference')
        regular(c['entries'][path])
    def command(value):
        inert(value); require(shlex.split(value), 'nonexpanding argv')
        require(len([q for q in c['checks'] if q['command'] == value]) == 1, 'component command linkage')
    def number(value, positive=False):
        require(type(value) in (int, float) and math.isfinite(value) and value >= (1 if positive else 0), 'numeric bound')
    if 'tested_commit' in r:
        require(r['tested_commit'] == c['T'], 'report T')
    if 'base_commit' in r:
        require(r['base_commit'] == c['B'], 'report B')
    if form == 'controller_receipt':
        require(r['tree'] == c['tree'] and r['status'] == 'PASS' and r['test_only'] is True, 'controller claim')
        for section in ('snapshot', 'policy', 'worker'):
            require(r[section]['base'] == c['B'] and r[section]['head'] == c['T'], 'controller B/T')
        w = r['worker']; require(w['status'] == 'PASS', 'worker claim')
        require(r['policy']['full_database_required'] is True and w['full_database_required'] is True, 'DB claim')
        unique([q['check_id'] for q in w['checks']])
        for q in w['checks']:
            require(q['argv'] and all(isinstance(s, str) for s in q['argv']), 'component argv')
            for s in q['argv']: inert(s)
            require(type(q['exit_code']) is int and q['exit_code'] == 0 and q['interrupted'] is False, 'component claim')
            number(q['duration_seconds']); number(q['stdout']['bytes']); hexstr(q['stdout']['sha256'], 64)
            canonical(q['stdout']['path']); ref(str(Path(c['report_ref']).parent / q['stdout']['path']))
        for p, digest in w['artifacts'].items():
            canonical(p); hexstr(digest, 64); ref(str(Path(c['report_ref']).parent / p))
        require(w['container_removed'] is True and w['volume_removed'] is True, 'cleanup claim')
        require(all(w['database'][k] == 0 for k in ('errors', 'failures', 'skipped')), 'database failures')
        number(w['database']['tests'], True)
        for key in ('container', 'image', 'volume'): inert(w[key])
        for mount in w['mounts']:
            for value in mount.values(): inert(value)
        for key in ('changed_paths', 'requiring_paths'):
            unique(r['policy'][key])
            for path in r['policy'][key]: canonical(path)
    elif form == 'integrity_report':
        u = r['result_commit']; hexstr(u, 40)
        require((c['T'], u) in c['ancestry'] and (u, c['R']) in c['ancestry'], 'intermediate U lineage')
        require(r['audit']['base'] == c['B'] and r['audit']['head'] == u and r['audit']['identity'] == c['D'], 'audit identity')
        require(r['status'] == r['governance_schema'] == 'PASS' and not r['suffix'] and not r['audit']['errors'] and r['full_database_required'] is True, 'integrity claims')
        for value in (r['selected_raw_bytes'], r['reconstructed_artifacts'], r['audit']['stored_bytes'], r['audit']['files']): number(value)
    elif form == 'comparison_report':
        require(r['same_collection_all_runs'] is True, 'comparison claim'); number(r['tests'], True)
        companions = [q for q in c['companions'] if q['ref'] in c['reviews'][0]['evidence_refs'] and q['ref'] in c['declared_files']]
        require(len(companions) == 1, 'benchmark companion uniqueness')
        q = companions[0]; ref(q['ref']); require(q['hash_M'] == q['hash_current'] == sha(json.dumps(q['report'], sort_keys=True).encode()), 'companion immutable')
        grammar(q['report'], catalog['profiles']['benchmark_index']['schema'])
        require(q['report']['tested_commit'] == c['T'] and q['report']['base_commit'] == c['B'], 'companion B/T')
        final = q['report']['final_runs']; unique([x['label'] for x in final]); unique([x['run'] for x in r['runs']])
        require({x['label'] for x in final} == {x['run'] for x in r['runs']}, 'comparison run identities')
        for item in r['runs']:
            bound = next(x for x in final if x['label'] == item['run'])
            require(all(item[k] == bound[k] for k in ('workers', 'tests', 'exit_code', 'wall_seconds')), 'comparison fields')
            require(item['tests'] == r['tests'] and item['exit_code'] == 0, 'comparison tests/exit')
            number(item['workers'], True); number(item['wall_seconds'])
            require(item['phase_outcomes']['failed'] == item['phase_outcomes']['skipped'] == 0, 'comparison failure claims')
            for value in item['phase_outcomes'].values(): number(value)
    elif form == 'scope_report':
        unique(r['files_changed'])
        for p in r['files_changed']: canonical(p)
        require(set(r['files_changed']) <= set(c['declared_files']), 'scope declared subset')
        require(r['frozen_and_execution_policy_unchanged'] is True and not r['errors'], 'scope claim')
        require(r['requirements_status'].startswith('NOT_RUN:') and r['requirements_status'].split(':', 1)[1].strip(), 'requirements nonPASS')
        inert(r['compatibility_note']); unique(r['pinned_controller_assets_changed'])
        for p in r['pinned_controller_assets_changed']:
            canonical(p)
            require(len([q for q in r['files_changed'] if q == p or ('/' not in p and Path(q).name == p)]) == 1, 'scope basename linkage')
    elif form == 'benchmark_index':
        codec = r['codec_source']; hexstr(codec['source_revision'], 40); hexstr(codec['source_git_blob'], 40); hexstr(codec['sha256'], 64)
        require(type(codec['upstream_pr']) is int and codec['upstream_pr'] > 0, 'codec PR'); inert(codec['use'])
        require(c['codec_use'] == 'CLAIM_ONLY' and c['codec_reads'] == [], 'codec source nonverification')
        unique([x['label'] for x in r['final_runs']]); unique([(x['label'], x['tested_commit']) for x in r['development_runs']])
        for run in r['final_runs']:
            require(run['tested_commit'] == c['T'] and type(run['exit_code']) is int and run['exit_code'] == 0, 'final run identity/exit')
            number(run['tests'], True); number(run['workers'], True); number(run['wall_seconds']); hexstr(run['nodes_sha256'], 64); command(run['command'])
            for path in run['artifacts'].values(): ref(path)
        for run in r['development_runs']:
            hexstr(run['tested_commit'], 40); require(run['tested_commit'] != c['T'], 'development cannot substitute final')
            require(type(run['exit_code']) is int, 'development exit'); inert(run['command']); number(run['workers'], True); number(run['wall_seconds'])
            for path in run['artifacts'].values(): ref(path)
        for q in r['quality'].values():
            require(type(q['exit_code']) is int and q['exit_code'] == 0, 'quality exit'); number(q['wall_seconds']); command(q['command'])
            for path in q['artifacts'].values(): ref(path)
        unique([q['ref'] for q in r['roundtrips']])
        for q in r['roundtrips']: ref(q['ref']); hexstr(q['raw_sha256'], 64); number(q['raw_bytes'])
        for q in r['excluded_development_artifacts']:
            inert(q['original_path']); inert(q['reason']); hexstr(q['raw_sha256'], 64); number(q['raw_bytes'])


def inventory(entries, count, native_complete=True, label='COMPLETE_WITH_LIMITATIONS'):
    require(native_complete is True, 'inventory native incomplete')
    require(type(count) is int and count >= 0, 'inventory integer count')
    require(all(entry == OBS for entry in entries), 'typed entry limitation')
    require(count == len(entries), 'exact documentary count')
    require(not entries or label == 'COMPLETE_WITH_LIMITATIONS', 'visible unverified limitations')
    return {'documentary_unverified_count': count, 'entries': entries, 'summary': label}


def object_at(revision, path):
    canonical(path); hexstr(revision, 40)
    entry = git('ls-tree', '-z', revision, '--', path).rstrip(b'\0').decode()
    header, actual = entry.split('\t'); require(actual == path, 'exact Git path')
    fields = header.split(); regular(fields)
    raw = git('cat-file', 'blob', fields[2]); require(len(raw) <= 4 * 1024**2, 'research blob bound')
    return raw, fields


def context(row, report_pin, form, raw, record, review, catalog):
    d = row['owner'].split('/')[-1]
    c = {'form': form, 'D': d, 'owner': row['owner'], 'B': row['base'], 'T': row['tested'], 'R': row['reviewed'], 'M': row['original_merge'],
         'protected_base': BASE, 'validation_revision': BASE, 'tree': git('rev-parse', row['tested'] + '^{tree}').decode().strip(),
         'record_ref': row['record'], 'review_ref': 'docs/exec-plans/reviews/' + d + '/GENERAL.json', 'report_ref': report_pin['path'],
         'record_owner': record['change_identity'], 'record_B': record['base_commit'], 'record_T': record['tested_commit'],
         'record_versions': dict.fromkeys(('R', 'M', 'current'), row['record_sha256']),
         'report_hash_M': sha(raw), 'report_hash_current': sha(raw), 'reviews': [review],
         'checks': record['checks_run'], 'declared_files': record['files_changed'], 'authority': [], 'entries': {},
         'purpose': 'GLOBAL_ARCHIVAL_GOVERNANCE_INVENTORY', 'selected_aliases': ['harness-governance-v0.1/HG-062', 'HG-062'],
         'cache_kind': 'DOCUMENTARY_ONLY', 'profile_version': catalog['draft_version'], 'native_complete': True, 'decoder': 'NATIVE_ALLOWED',
         'selection_basis': 'ORIGINAL_LINKAGE', 'usage': dict.fromkeys(LIMITS, 0), 'observations': [], 'codec_use': 'CLAIM_ONLY', 'codec_reads': [],
         'merge_candidates': [row['original_merge']], 'protected_first_parent': git('rev-list', '--first-parent', BASE).decode().splitlines(),
         'ancestry': set(), 'companions': []}
    checks = [q for q in record['checks_run'] if q['evidence_ref'] == report_pin['path']]; require(len(checks) == 1, 'original report check')
    c.update(check_id=checks[0]['check_id'], command=checks[0]['command'])
    revisions = [c[x] for x in ('B', 'T', 'R', 'M', 'protected_base')]
    r = strict(raw)
    if form == 'integrity_report': revisions.insert(2, r['result_commit'])
    for i, a in enumerate(revisions):
        for b in revisions[i:]:
            require(subprocess.run(['git', 'merge-base', '--is-ancestor', a, b], cwd=ROOT, capture_output=True).returncode == 0, 'original lineage')
            c['ancestry'].add((a, b))
    for path in AUTH_PATHS:
        a = {'path': path}
        for key, rev in [('T', c['T']), ('R', c['R'])]:
            index = strict(object_at(rev, 'CURRENT_DOCUMENT_INDEX.json')[0])
            entries = [x for x in index['documents'] + index['machine_readable'] if x['path'] == path]; require(len(entries) == 1, 'original index path')
            content, _ = object_at(rev, path); a[key + '_hash'] = sha(content); a[key + '_index_hash'] = entries[0]['sha256']
            if path.endswith('.schema.json'):
                grammar(record if path == 'HARNESS_CHANGE.schema.json' else review, strict(content))
        c['authority'].append(a)
    references = {c['record_ref'], c['report_ref'], c['review_ref']}
    if form == 'controller_receipt':
        references |= {str(Path(c['report_ref']).parent / q['stdout']['path']) for q in r['worker']['checks']}
        references |= {str(Path(c['report_ref']).parent / p) for p in r['worker']['artifacts']}
    if form == 'benchmark_index':
        for run in r['final_runs'] + r['development_runs'] + list(r['quality'].values()): references.update(run['artifacts'].values())
        references.update(q['ref'] for q in r['roundtrips'])
    if form == 'comparison_report':
        # Bounded research selection: only original explicitly review-linked report pins.
        for pin in row['reports']:
            if pin['path'] in review['evidence_refs'] and pin['path'] in record['files_changed']:
                qraw, _ = object_at(c['M'], pin['path']); value = strict(qraw)
                if jsonschema.Draft202012Validator(catalog['profiles']['benchmark_index']['schema']).is_valid(value):
                    require(object_at(BASE, pin['path'])[0] == qraw, 'companion byte equality')
                    digest = sha(json.dumps(value, sort_keys=True).encode())
                    c['companions'].append({'ref': pin['path'], 'report': value, 'hash_M': digest, 'hash_current': digest}); references.add(pin['path'])
    require(len(references) <= 512, 'secondary metadata budget')
    entries = git('ls-tree', '-z', c['M'], '--', *sorted(references)).decode().split('\0')
    for line in filter(None, entries):
        header, path = line.split('\t'); c['entries'][path] = header.split()
    require(set(c['entries']) == references, 'secondary exact metadata coverage')
    c['usage']['metadata_entries'] = len(references)
    return c


def neutral(c, report):
    """Injectively rename all owner/revision/path/command slots, retaining structure."""
    mapping = {c['D']: 'HG-913', c['owner']: 'harness-governance-v0.1/HG-913'}
    revisions = set(sum(([a, b] for a, b in c['ancestry']), [])) | {c[k] for k in ('tree', 'validation_revision')}
    mapping.update({r: sha(('fixture-' + r).encode())[:40] for r in revisions})
    paths = set(c['entries']) | set(c['declared_files'])
    # Preserve basename relationships while changing owner-neutral ordinary directories.
    for path in paths:
        mapping[path] = path.replace(c['D'], 'HG-913') if c['D'] in path else 'fixture/' + path
    mapping[c['record_ref']] = 'docs/exec-plans/governance/HG-913.yaml'
    mapping[c['review_ref']] = 'docs/exec-plans/reviews/HG-913/GENERAL.json'
    for check in c['checks']: mapping[check['command']] = '/fixture/python -m specimen ' + sha(check['command'].encode())[:12]
    # Do not rename indexed authority paths, which are fixed contract roles.
    def rewrite(value):
        if isinstance(value, str):
            if value in mapping: return mapping[value]
            return value.replace(c['D'], 'HG-913')
        if isinstance(value, dict): return {rewrite(k): rewrite(v) for k, v in value.items()}
        if isinstance(value, list): return [rewrite(x) for x in value]
        if isinstance(value, tuple): return tuple(rewrite(x) for x in value)
        if isinstance(value, set): return {rewrite(x) for x in value}
        return value
    n, r = rewrite(c), rewrite(report)
    n['authority'] = copy.deepcopy(c['authority'])
    # Fixed canonical schema role names remain unchanged, including report grammar keys.
    if c['form'] == 'scope_report':
        r['pinned_controller_assets_changed'] = [Path(p).name if '/' not in original else p for p, original in zip(r['pinned_controller_assets_changed'], report['pinned_controller_assets_changed'])]
    raw = json.dumps(r).encode(); n['report_hash_M'] = n['report_hash_current'] = sha(raw)
    for q in n['companions']: q['hash_M'] = q['hash_current'] = sha(json.dumps(q['report'], sort_keys=True).encode())
    return n, raw


def fixture_matrix(contexts, catalog):
    done = {}
    def run(name, form='scope_report', mutate=None, expected='INVALID', raw_transform=None):
        c, raw = copy.deepcopy(contexts[form]); report = strict(raw)
        if mutate: mutate(c, report)
        raw = json.dumps(report).encode(); c['report_hash_M'] = c['report_hash_current'] = sha(raw)
        if raw_transform:
            raw = raw_transform(raw)
            if name != 'report-changed':
                c['report_hash_M'] = c['report_hash_current'] = sha(raw)
        try:
            outcome = classify(raw, c, catalog)
            actual = outcome['documentary_validation'] if isinstance(outcome, dict) else outcome
            if isinstance(outcome, dict): require(outcome == OBS, 'all typed limitations')
        except (ValueError, TypeError, KeyError, jsonschema.ValidationError, UnicodeError, RecursionError): actual = 'INVALID'
        require(actual == expected, f'fixture {name}: {actual} != {expected}')
        done[name] = actual
    for form in contexts:
        run('owner-neutral-' + form, form, expected='BOUND_ORIGINAL_CLAIM')
    positive = {'original_controller': 'controller_receipt', 'original_integrity_with_preserved_RRO_failure': 'integrity_report',
                'original_comparison': 'comparison_report', 'original_scope_declared_subset': 'scope_report',
                'original_benchmark_parallel_codec_claim_only_no_companion_scan': 'benchmark_index',
                'owner_neutral_equivalent_each_form': 'scope_report', 'inert_absolute_host_attribution': 'controller_receipt',
                'distinct_development_130_preserved': 'benchmark_index', 'codec_source_identity_unverified': 'benchmark_index'}
    for name, form in positive.items(): run(name, form, expected='BOUND_ORIGINAL_CLAIM')
    def put(key, value): return lambda c, r: c.__setitem__(key, value)
    cases = {
      'unknown_form': put('form', 'invented'),
      'unknown_nested_field': lambda c,r: r.__setitem__('unknown', {}),
      'wrong_scalar_type': lambda c,r: r.__setitem__('frozen_and_execution_policy_unchanged', 1),
      'invalid_revision_or_hash': put('T', '123'),
      'missing_or_ambiguous_original_merge': put('merge_candidates', []),
      'original_merge_not_protected_first_parent': put('protected_first_parent', []),
      'wrong_namespaced_owner': put('owner', 'different/HG-913'),
      'wrong_B_T_R_lineage': put('ancestry', set()),
      'record_absent_R': lambda c,r: c['record_versions'].__setitem__('R', None),
      'record_or_report_changed_since_M': lambda c,r: c['record_versions'].__setitem__('current', 'changed'),
      'symlink_submodule_or_directory': lambda c,r: c['entries'].__setitem__(c['report_ref'], ['120000','blob','a'*40]),
      'missing_or_ambiguous_original_GENERAL': put('reviews', []),
      'review_owner_or_R_mismatch': lambda c,r: c['reviews'][0].__setitem__('reviewed_head_sha', 'a'*40),
      'missing_direct_or_one_record_link': lambda c,r: c['reviews'][0].__setitem__('evidence_refs', []),
      'extra_reference_hop': lambda c,r: c['reviews'][0].__setitem__('evidence_refs', ['docs/exec-plans/evidence/HG-913/other.json']),
      'original_index_hash_mismatch': lambda c,r: c['authority'][0].__setitem__('T_index_hash', '0'*64),
      'changed_T_R_original_authority': lambda c,r: c['authority'][0].__setitem__('R_hash', '0'*64),
      'duplicate_report_check_ref': lambda c,r: c['checks'].append(next(x for x in c['checks'] if x['evidence_ref']==c['report_ref'])),
      'command_or_T_mismatch': put('command', '/fixture/python changed'),
      'scope_undeclared_duplicate_or_ambiguous_basename': lambda c,r: r['files_changed'].append('undeclared/path'),
      'native_strict_decoder_denial': put('decoder', 'DENIED'),
      'false_affirmative_or_nonempty_failure_collection': lambda c,r: r['errors'].append('failure'),
      'unauthenticated_observation_input': put('observations', [{'exit_code':0}]),
      'unfinished_native_inventory': put('native_complete', False),
      'selected_owner_or_alias': lambda c,r: c['selected_aliases'].append(c['owner']),
      'new_current_self_archival': put('merge_candidates', []),
      'unknown_purpose': put('purpose', 'UNKNOWN'),
      'selected_or_review_consumer': put('purpose', 'SELECTED_REVIEW'),
      'prerequisite_M3_requirement_consumer': put('purpose', 'M3'),
      'storage_history_decoder_source_consumer': put('purpose', 'STORAGE_HISTORY'),
      'install_admit_App_release_consumer': put('purpose', 'ADMISSION'),
      'execution_decoder_RRO_cache_reuse': put('cache_kind', 'EXECUTION'),
      'each_byte_node_depth_git_entry_budget_exhausted': lambda c,r: c['usage'].__setitem__('git_operations', 65),
      'classification_from_PASS_or_sample_identity': put('selection_basis', 'PASS'),
    }
    for name, mutation in cases.items(): run(name, mutate=mutation)
    run('missing_or_duplicate_benchmark_companion', 'comparison_report', put('companions', []))
    run('codec_tuple_malformed_or_reused_as_source_availability', 'benchmark_index', put('codec_use', 'SOURCE_AVAILABLE'))
    run('duplicate_JSON_key', raw_transform=lambda b: b[:-1] + b',"errors":[]}')
    run('nonfinite_BOM_trailing_JSON', raw_transform=lambda b: b'\xef\xbb\xbf' + b)
    run('malformed_main_storage_envelope', mutate=put('decoder', 'MALFORMED_ENVELOPE'))
    for name, state, exit_code in [('known_exact_parent_nonzero','COMPLETED',1), ('known_exact_parent_interrupted','INTERRUPTED',130),
                                  ('known_exact_parent_unstarted','UNSTARTED',None), ('known_exact_parent_incomplete','INCOMPLETE',None),
                                  ('known_exact_parent_failure_or_skip','FAILED',0)]:
        run(name, mutate=lambda c,r,s=state,e=exit_code: c['observations'].append(Native(tuple_for(c),s,e,TOKEN)))
    run('HG055_and_owner_neutral_observed_parent_exit0', mutate=lambda c,r: c['observations'].append(Native(tuple_for(c),'COMPLETED',0,TOKEN)), expected='ORDINARY_NATIVE_EXIT_BINDING_ONLY')
    for bound, value in LIMITS.items():
        run('budget-' + bound, mutate=lambda c,r,k=bound,v=value: c['usage'].__setitem__(k,v+1))
        run('budget-inclusive-' + bound, mutate=lambda c,r,k=bound,v=value: c['usage'].__setitem__(k,v), expected='BOUND_ORIGINAL_CLAIM')
    for purpose in ['SELECTED_TASK','SELECTED_GOVERNANCE','REVIEW','PREREQUISITE','REQUIREMENT','STORAGE','HISTORY','DECODER','SOURCE','INSTALL','APP','RELEASE']:
        run('caller-' + purpose, mutate=put('purpose',purpose))
    for kind in ['DECODER','RRO','SOURCE','STORAGE','SELECTED']:
        run('cache-' + kind, mutate=put('cache_kind',kind))
    for mode, typ in [('160000','commit'),('040000','tree')]: run('mode-' + mode, mutate=lambda c,r,m=mode,t=typ: c['entries'].__setitem__(c['report_ref'],[m,t,'a'*40]))
    for name, transform in [('trailing',lambda b:b+b'{}'),('nonfinite',lambda b:b.replace(b'"errors": []',b'"errors": [NaN]')),
                             ('invalid-utf8',lambda b:b'\xff'),('deep-json',lambda b:b'['*65+b'0'+b']'*65),('oversized-json',lambda b:b' '*1048577)]:
        run('bytes-' + name,raw_transform=transform)
    run('nested-unknown', 'controller_receipt', lambda c,r:r['worker']['database'].__setitem__('unknown',1))
    run('integer-token', 'benchmark_index', lambda c,r:r['codec_source'].__setitem__('upstream_pr',1.0))
    run('codec-hash', 'benchmark_index', lambda c,r:r['codec_source'].__setitem__('sha256','bad'))
    run('codec-no-scan', 'benchmark_index', put('codec_reads',['invented-source']))
    run('duplicate-scope', mutate=lambda c,r:r['files_changed'].append(r['files_changed'][0]))
    run('ambiguous-scope-basename', mutate=lambda c,r:(r['files_changed'].append('other/validate_harness.py'),c['declared_files'].append('other/validate_harness.py')))
    run('false-affirmative', mutate=lambda c,r:r.__setitem__('frozen_and_execution_policy_unchanged',False))
    for path in ['/absolute','../up','a/./b','a\\b','a\x00b','a\nb']:
        run('path-' + repr(path),mutate=lambda c,r,p=path:r['files_changed'].append(p))
    run('report-changed', raw_transform=lambda b:b+b' ')
    run('conflicting-parent', mutate=lambda c,r:c['observations'].extend([Native(tuple_for(c),'COMPLETED',0,TOKEN),Native(tuple_for(c),'COMPLETED',1,TOKEN)]))
    run('selected-display-alias', mutate=lambda c,r:c['selected_aliases'].append(c['D']))
    run('distinct-child-nonzero', mutate=lambda c,r:c['observations'].append(Native(tuple_for(c)[:-1]+('other-report',),'INTERRUPTED',130,TOKEN)),expected='BOUND_ORIGINAL_CLAIM')
    for count in [0,1,5]:
        require(inventory([dict(OBS) for _ in range(count)], count)['documentary_unverified_count']==count,'inventory cardinality')
        done['inventory-valid-'+str(count)]='COMPLETE_WITH_LIMITATIONS'
    for name, entries, count, complete, label in [('zero-mismatch',[OBS],0,True,'COMPLETE_WITH_LIMITATIONS'),('nonzero-mismatch',[],1,True,'COMPLETE_WITH_LIMITATIONS'),('bool',[],False,True,'COMPLETE_WITH_LIMITATIONS'),('missing',[],None,True,'COMPLETE_WITH_LIMITATIONS'),('hidden',[OBS],1,True,'ALL_HISTORICAL_EXECUTION_VERIFIED'),('native',[],0,False,'COMPLETE_WITH_LIMITATIONS'),('typed',[dict(OBS,semantic_validation='VERIFIED')],1,True,'COMPLETE_WITH_LIMITATIONS')]:
        try: inventory(entries,count,complete,label)
        except ValueError: done['inventory-invalid-'+name]='INVALID'
        else: raise ValueError('inventory accepted '+name)
    # Each form's hostile scalar/claim/reference probes operate on real report fields.
    extra = [
        ('controller-parent-not-child', 'controller_receipt', lambda c,r: r['worker']['checks'][0].__setitem__('exit_code', 1)),
        ('controller-interrupted', 'controller_receipt', lambda c,r: r['worker']['checks'][0].__setitem__('interrupted', True)),
        ('controller-false-test-only', 'controller_receipt', lambda c,r: r.__setitem__('test_only', False)),
        ('controller-host-control', 'controller_receipt', lambda c,r: r['worker'].__setitem__('container', 'bad\nvalue')),
        ('integrity-errors', 'integrity_report', lambda c,r: r['audit']['errors'].append('failure')),
        ('integrity-U', 'integrity_report', lambda c,r: r.__setitem__('result_commit', 'b'*40)),
        ('comparison-false', 'comparison_report', lambda c,r: r.__setitem__('same_collection_all_runs', False)),
        ('comparison-missing-run', 'comparison_report', lambda c,r: r['runs'].pop()),
        ('comparison-fields', 'comparison_report', lambda c,r: r['runs'][0].__setitem__('workers', 37)),
        ('comparison-duplicate-companion', 'comparison_report', lambda c,r: c['companions'].append(c['companions'][0])),
        ('scope-requirement-PASS', 'scope_report', lambda c,r: r.__setitem__('requirements_status', 'PASS')),
        ('benchmark-final-T', 'benchmark_index', lambda c,r: r['final_runs'][0].__setitem__('tested_commit', 'c'*40)),
        ('benchmark-command', 'benchmark_index', lambda c,r: r['quality']['lint'].__setitem__('command', 'unbound command')),
        ('benchmark-development-T', 'benchmark_index', lambda c,r: r['development_runs'][0].__setitem__('tested_commit', c['T'])),
        ('benchmark-artifact', 'benchmark_index', lambda c,r: r['final_runs'][0]['artifacts'].__setitem__('pytest.log', 'docs/exec-plans/evidence/HG-913/missing')),
        ('benchmark-roundtrip-duplicate', 'benchmark_index', lambda c,r: r['roundtrips'].append(r['roundtrips'][0])),
    ]
    for name, form, mutation in extra: run(name, form, mutation)
    for form in contexts:
        run('form-extra-'+form, form, lambda c,r:r.__setitem__('unrecognized', True))
        run('form-missing-'+form, form, lambda c,r:r.pop(next(iter(r))))
    run('bytes-node-exhaustion', raw_transform=lambda b:b'['+b'0,'*262144+b'0]')
    matrix = strict((HERE/'DECISION_MATRIX.json').read_bytes())
    for row in matrix['positive_cases'] + matrix['negative_cases'] + [matrix['observed_exit_control']]:
        require(done[row['case']] == row['expected'], 'matrix coverage '+row['case'])
    return done


def preservation(base, tested):
    old = git('show',base+':tools/harness/validate_harness.py').decode(); new = git('show',tested+':tools/harness/validate_harness.py').decode()
    def spans(source):
        lines=source.splitlines(keepends=True)
        return {n.name:''.join(lines[n.lineno-1:n.end_lineno]) for n in ast.parse(source).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
    before,after=spans(old),spans(new)
    require(set(after)-set(before)=={'historical_documentary_projection_errors'},'only own projection helper')
    require([n for n in before if before[n]!=after[n]]==['governance_allowed_patterns','validate'],'only own governance dispatch')
    restored = new
    a=restored.index('HG062_ALLOWED_PATTERNS ='); b=restored.index('HG061_ALLOWED_PATTERNS =',a)
    restored=restored[:a]+restored[b:]
    a=restored.index('def historical_documentary_projection_errors'); b=restored.index('def governance_allowed_patterns',a)
    restored=restored[:a]+restored[b:]
    restored=restored.replace("    if change_id == 'HG-062':\n        return HG062_ALLOWED_PATTERNS\n", '')
    restored=restored.replace("                if change_id == 'HG-062':\n                    errors.extend(historical_documentary_projection_errors(record, changed_task_ids))\n", '')
    restored=restored.replace("'HG-060', 'HG-061', 'HG-062')", "'HG-060', 'HG-061')")
    require(restored == old, 'exact governance-only reversible delta')
    contract=git('show',tested+':docs/harness/HARNESS_GOVERNANCE_CONTRACT.md')
    require(contract.startswith(git('show',base+':docs/harness/HARNESS_GOVERNANCE_CONTRACT.md')+b'\n'),'old contracts preserved prefix')
    allowed={'CURRENT_DOCUMENT_INDEX.json','HARNESS_DOCUMENT_MANIFEST.json','tools/harness/validate_harness.py','tests/harness/test_validator.py','docs/harness/HARNESS_GOVERNANCE_CONTRACT.md','docs/exec-plans/active/HG-058.md'}
    changed=git('diff','--name-only',base,tested).decode().splitlines()
    require(all(p in allowed or p.startswith('docs/exec-plans/evidence/HG-062/') or p.startswith('docs/exec-plans/reviews/HG-062/') or p=='docs/exec-plans/governance/HG-062.yaml' for p in changed),'literal scope')
    manifest=json.loads(git('show',tested+':HARNESS_DOCUMENT_MANIFEST.json'))
    require('docs/exec-plans/governance/HG-062.yaml' not in {e['path'] for e in manifest['files']},'no mutable result manifest registration')
    return {'unchanged_existing_functions':len(before)-2,'changed_functions':['governance_allowed_patterns','validate'],'paths':len(changed),'old_contract_prefix_preserved':True}


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--base',required=True);parser.add_argument('--tested',required=True);parser.add_argument('--research-only',action='store_true');args=parser.parse_args()
    require(args.base==BASE,'assigned base')
    manifest=strict((HERE/'REVIEW_INPUTS.json').read_bytes())
    require(sha((HERE/'REVIEW_INPUTS.json').read_bytes())=='51b74b34a858a7d5d487d356cb9ff7e2d9a2819d699f30dadfafd0a268840960','exact preparation manifest')
    for name,digest in manifest['files'].items(): require(sha((HERE/name).read_bytes())==digest,'preparation hash '+name)
    require(sha((HERE/'PACKET.md').read_bytes())=='8fde831c4094387ced06a3fed98d2a286ddc58c4987595dde4cfd1abb65ad041','assigned packet hash')
    catalog=strict((HERE/'CLOSED_DOCUMENTARY_FORMS.json').read_bytes())
    require(len(catalog['profiles'])==5,'five forms')
    def closed(s):
        require('$ref' not in s,'no remote schema references')
        if s.get('type')=='object':
            require(s.get('additionalProperties') is False and set(s['properties'])==set(s['required']),'closed object')
            for v in s['properties'].values(): closed(v)
        if s.get('type')=='array': require('maxItems' in s,'bounded arrays');closed(s['items'])
        for q in s.get('anyOf',[]): closed(q)
    for p in catalog['profiles'].values(): closed(p['schema'])
    bindings=strict((HERE/'ORIGINAL_BINDINGS.json').read_bytes());contexts={};research=[]
    for row in bindings['rows']:
        raw_record,_=object_at(row['original_merge'],row['record']);require(sha(raw_record)==row['record_sha256'],'record pin')
        require(raw_record==object_at(row['reviewed'],row['record'])[0]==object_at(BASE,row['record'])[0],'original record R/M/current bytes')
        record=yaml.safe_load(raw_record);review_path='docs/exec-plans/reviews/'+row['owner'].split('/')[-1]+'/GENERAL.json'
        raw_review,_=object_at(row['original_merge'],review_path);review=strict(raw_review);require(review==row['review'],'original GENERAL pin')
        for pin in row['reports']:
            raw,entry=object_at(row['original_merge'],pin['path']);require(sha(raw)==pin['sha256'] and len(raw)==pin['bytes'],'report pin')
            require((' '.join(entry)+'\t'+pin['path'])==pin['mode_blob'],'report object pin')
            require(raw==object_at(BASE,pin['path'])[0],'original report M/current equality')
            matches=[n for n,p in catalog['profiles'].items() if jsonschema.Draft202012Validator(p['schema']).is_valid(strict(raw))];require(len(matches)==1,'unique grammar sample')
            form=matches[0];c=context(row,pin,form,raw,record,review,catalog)
            require(classify(raw,c,catalog)==OBS,'original binding '+form)
            neutral_context,neutral_raw=neutral(c,strict(raw));require(classify(neutral_raw,neutral_context,catalog)==OBS,'neutral binding '+form)
            contexts[form]=(neutral_context,neutral_raw)
            research.append({'form':form,'owner':row['owner'],'report':pin['path'],'sha256':sha(raw),'B':c['B'],'T':c['T'],'R':c['R'],'M':c['M'],'validation_revision':BASE,'secondary_entries':c['usage']['metadata_entries'],'observation':OBS})
    cases=fixture_matrix(contexts,catalog)
    guards=preservation(args.base,args.tested) if not args.research_only else {'pre_T_affected_check_only':True}
    print(json.dumps({'meaning':'HG062 definition fixtures and immutable documentary research only; runtime recognition NOT_RUN; original computation/producer/review acceptance NOT_CERTIFIED','original_samples':research,'fixture_cases':cases,'fixture_case_count':len(cases),'preservation':guards,'typed_observation':OBS},indent=2))


if __name__=='__main__': main()
