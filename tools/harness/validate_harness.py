#!/usr/bin/env python3
"""Validate Harness contracts; Git arguments enable revision-bound PR checks."""
import argparse
import fnmatch
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKLOG = 'KineticLoop_Harness_Backlog_v0.2.json'
INDEX = 'CURRENT_DOCUMENT_INDEX.json'
MANIFEST = 'HARNESS_DOCUMENT_MANIFEST.json'
GOVERNANCE_SCHEMA = 'HARNESS_CHANGE.schema.json'
INTEGRATION_SCHEMA = 'INTEGRATION_RECORD.schema.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative_path(path):
    return (isinstance(path, str) and bool(path) and '\\' not in path
            and all(p not in ('', '.', '..') for p in path.split('/')))


def matches(path, patterns):
    """Match glob components; * cannot cross / and ** matches whole directories."""
    if not relative_path(path):
        return False

    def match(parts, pattern):
        if not pattern:
            return not parts
        if pattern[0] == '**':
            return match(parts, pattern[1:]) or bool(parts and match(parts[1:], pattern))
        return bool(parts and fnmatch.fnmatchcase(parts[0], pattern[0])
                    and match(parts[1:], pattern[1:]))

    return any(relative_path(p) and match(path.split('/'), p.split('/')) for p in patterns)


def unique_mapping(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate-key:' + str(key))
        result[key] = value
    return result


def load_artifact_text(text, suffix):
    if suffix == '.json':
        return json.loads(text, object_pairs_hook=unique_mapping)
    import yaml

    class StrictLoader(yaml.SafeLoader):
        pass

    def mapping(loader, node):
        loader.flatten_mapping(node)
        return unique_mapping((loader.construct_object(k), loader.construct_object(v))
                              for k, v in node.value)

    StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    try:
        return yaml.load(text, Loader=StrictLoader)
    except yaml.YAMLError as ex:
        raise ValueError('yaml-parse:' + str(ex)) from ex


def load_artifact(path):
    return load_artifact_text(path.read_text(), path.suffix)


def section(text, heading):
    match = re.search(r'^## ' + re.escape(heading) + r'\s*\n(.*?)(?=^## |\Z)', text, re.M | re.S)
    return match.group(1) if match else None


def subsection(text, heading):
    match = re.search(r'^### ' + re.escape(heading) + r'\s*\n(.*?)(?=^## |^### |\Z)',
                      text, re.M | re.S)
    return match.group(1) if match else None


def bullets(text):
    return [line[2:].strip() for line in text.splitlines() if line.startswith('- ')]


def packet_errors(task, text):
    errors = []
    name = task['id']
    if task['task_identity'] not in text:
        errors.append('packet-identity:' + name)
    if task['status'] == 'SUPERSEDED':
        return errors
    if task['title'] not in text:
        errors.append('packet-title:' + name)
    deps = section(text, 'Dependencies')
    if deps is None or set(re.findall(r'KL-[0-9]{3}[A-Z]?', deps.split('### Conditional dependencies')[0])) != set(task['depends_on']):
        errors.append('packet-deps:' + name)
    conditional = subsection(text, 'Conditional dependencies')
    expected_conditional = {
        dependency if isinstance(dependency, str)
        else dependency['task_id'] + ' when ' + dependency['condition']
        for dependency in task.get('conditional_depends_on', [])
    }
    found_conditional = set() if conditional is None else {
        value for value in bullets(conditional) if value != 'none'
    }
    if conditional is None or found_conditional != expected_conditional:
        errors.append('packet-conditional-deps:' + name)
    checks = section(text, 'Checks required for this task PR')
    if checks is None or sorted(bullets(checks)) != sorted(task['checks_required_for_this_task']):
        errors.append('packet-checks:' + name)
    if task.get('write_paths_status') == 'ENFORCEABLE':
        scope = section(text, 'Resource / write isolation') or ''
        resource_block = re.search(r'^Resource keys:\s*\n((?:- [^\n]+\n?)+)', scope, re.M)
        expected_resources = set(task.get('resource_keys', []))
        found_resources = set() if not resource_block else {
            value for value in bullets(resource_block.group(1)) if value != 'none'
        }
        if found_resources != expected_resources:
            errors.append('packet-resource-keys:' + name)
        found = re.search(r'^Expected (?:implementation )?write paths:\s*\n((?:- [^\n]+\n?)+)', scope, re.M)
        if not found or sorted(bullets(found.group(1))) != sorted(task['write_paths']):
            errors.append('packet-write-paths:' + name)
    return errors


def git(root, *args):
    proc = subprocess.run(['git', *args], cwd=root, capture_output=True)
    if proc.returncode:
        raise ValueError('git:' + proc.stderr.decode(errors='replace').strip())
    return proc.stdout


def resolve(root, ref):
    # --end-of-options prevents a user-supplied ref from becoming a Git option.
    return git(root, 'rev-parse', '--verify', '--end-of-options', ref + '^{commit}').decode().strip()


def changed_paths(root, before, after):
    return git(root, 'diff', '--no-renames', '--name-only', '-z', before, after, '--').decode().split('\0')[:-1]


def result_paths(task_id):
    return [f'docs/exec-plans/completed/{task_id}_RESULT.{ext}' for ext in ('yaml', 'json')]


def evidence_pattern(task_id):
    return f'docs/exec-plans/evidence/{task_id}/**'


def review_patterns(task_id):
    return [f'docs/exec-plans/reviews/{task_id}/**']


def governance_record_paths(change_id):
    return [f'docs/exec-plans/governance/{change_id}.{ext}' for ext in ('yaml', 'json')]


def governance_allowed_patterns(change_id):
    return [
        BACKLOG,
        INDEX,
        MANIFEST,
        GOVERNANCE_SCHEMA,
        INTEGRATION_SCHEMA,
        '.github/workflows/**',
        'docs/exec-plans/active/**',
        f'docs/exec-plans/evidence/{change_id}/**',
        'docs/exec-plans/integrations/**',
        f'docs/exec-plans/reviews/{change_id}/**',
        f'docs/exec-plans/governance/{change_id}.yaml',
        f'docs/exec-plans/governance/{change_id}.json',
        'docs/harness/**',
        'tests/harness/**',
        'tools/harness/**',
    ]


def configure_ci_merge_gate(root, args):
    """Bind a PR checkout to one task result or one Harness governance record."""
    if not args.ci_pr_base or not args.ci_pr_head:
        raise ValueError('ci-revisions-required')
    base, head = resolve(root, args.ci_pr_base), resolve(root, args.ci_pr_head)
    if resolve(root, 'HEAD') != head:
        raise ValueError('ci-head-not-checked-out')
    git(root, 'merge-base', '--is-ancestor', base, head)
    task_candidates = []
    governance_candidates = []
    for path in changed_paths(root, base, head):
        match = re.fullmatch(r'docs/exec-plans/completed/(KL-[0-9]{3}[A-Z]?)_RESULT\.(?:yaml|json)', path)
        if match:
            task_candidates.append(match.group(1))
        match = re.fullmatch(r'docs/exec-plans/governance/(HG-[0-9]{3})\.(?:yaml|json)', path)
        if match:
            governance_candidates.append(match.group(1))
    task_ids, change_ids = set(task_candidates), set(governance_candidates)
    if (len(task_ids), len(change_ids)) not in ((1, 0), (0, 1)):
        raise ValueError(f'ci-change-record-count:task={len(task_ids)},governance={len(change_ids)}')
    selected = next(iter(task_ids or change_ids))
    review_path = root / 'docs/exec-plans/reviews' / selected / 'GENERAL.json'
    if not review_path.is_file():
        raise ValueError('ci-general-review-missing:' + selected)
    review = load_artifact(review_path)
    if not isinstance(review, dict) or not isinstance(review.get('reviewed_head_sha'), str):
        raise ValueError('ci-general-review-invalid:' + selected)
    args.protected_base = base
    if task_ids:
        args.task_id = selected
        args.reviewed_head = review['reviewed_head_sha']
    else:
        args.governance_change_id = selected
        args.governance_reviewed_head = review['reviewed_head_sha']


def suffix_errors(root, start, end, task_id, kind):
    """Require ancestry and check every bookkeeping commit, including reverted changes."""
    errors = []
    try:
        start, end = resolve(root, start), resolve(root, end)
        git(root, 'merge-base', '--is-ancestor', start, end)
        commits = git(root, 'rev-list', '--reverse', start + '..' + end).decode().splitlines()
        allowed = review_patterns(task_id) if kind == 'review' else result_paths(task_id) + [evidence_pattern(task_id)]
        for commit in commits:
            parents = git(root, 'rev-list', '--parents', '-n', '1', commit).decode().split()[1:]
            if len(parents) != 1:
                errors.append(kind + '-suffix-merge:' + commit)
                continue
            for path in changed_paths(root, parents[0], commit):
                if not matches(path, allowed):
                    errors.append(kind + '-stale-change:' + path)
                elif kind == 'tested' and matches(path, [evidence_pattern(task_id)]):
                    exists = subprocess.run(['git', 'cat-file', '-e', parents[0] + ':' + path], cwd=root, capture_output=True)
                    if exists.returncode == 0:
                        errors.append('tested-evidence-not-addition:' + path)
    except ValueError as ex:
        errors.append(kind + '-revision:' + str(ex))
    return errors


def governance_suffix_errors(root, start, end, change_id, kind):
    """Restrict post-test and post-review governance bookkeeping commits."""
    errors = []
    try:
        start, end = resolve(root, start), resolve(root, end)
        git(root, 'merge-base', '--is-ancestor', start, end)
        commits = git(root, 'rev-list', '--reverse', start + '..' + end).decode().splitlines()
        allowed = (review_patterns(change_id) if kind == 'review'
                   else governance_record_paths(change_id) + [evidence_pattern(change_id)])
        for commit in commits:
            parents = git(root, 'rev-list', '--parents', '-n', '1', commit).decode().split()[1:]
            if len(parents) != 1:
                errors.append('governance-' + kind + '-suffix-merge:' + commit)
                continue
            for path in changed_paths(root, parents[0], commit):
                if not matches(path, allowed):
                    errors.append('governance-' + kind + '-stale-change:' + path)
                elif kind == 'tested' and matches(path, [evidence_pattern(change_id)]):
                    exists = subprocess.run(
                        ['git', 'cat-file', '-e', parents[0] + ':' + path],
                        cwd=root, capture_output=True)
                    if exists.returncode == 0:
                        errors.append('governance-tested-evidence-not-addition:' + path)
    except ValueError as ex:
        errors.append('governance-' + kind + '-revision:' + str(ex))
    return errors


def evidence_exists(root, ref):
    if not relative_path(ref):
        return False
    path = root / ref
    return path.is_file() and root.resolve() in path.resolve().parents


def semantic_result_errors(obj, task, root):
    errors = []
    if obj['task_identity'] != task['task_identity'] or obj['display_task_id'] != task['id']:
        errors.append('result-task-identity')
    if obj['task_status'] == 'PASS' and obj['task_checks_status'] != 'PASS':
        errors.append('pass-without-check-pass')
    commands = obj['commands_run']
    if obj['task_status'] == 'PASS' and not commands:
        errors.append('pass-empty-commands')
    check_ids = [c['check_id'] for c in commands]
    expected = set(task['checks_required_for_this_task'])
    if len(check_ids) != len(set(check_ids)) or set(check_ids) - expected:
        errors.append('result-check-ids')
    if obj['task_status'] == 'PASS' or obj['task_checks_status'] == 'PASS':
        if set(check_ids) != expected or any(c['result'] != 'PASS' for c in commands):
            errors.append('required-checks-not-pass')
    for c in commands:
        if c['result'] in ('PASS', 'FAIL') and not evidence_exists(root, c.get('evidence_ref')):
            errors.append('command-evidence:' + c['check_id'])
    for requirement in obj['requirements_covered']:
        if requirement['status'] in ('PASS', 'APPROVED_NA'):
            if not evidence_exists(root, requirement.get('evidence_ref')):
                errors.append('requirement-evidence:' + requirement['requirement_id'])
            if requirement.get('tested_commit') != obj['tested_commit']:
                errors.append('requirement-revision:' + requirement['requirement_id'])
            if '@' not in requirement['requirement_id']:
                errors.append('requirement-layer:' + requirement['requirement_id'])
    return errors


def requirement_ids(root):
    """Expand all requirement sources to concrete ID@layer obligations."""
    ids = set()
    sources = load_artifact(root / 'CURRENT_REQUIREMENT_SET.json')['sources']
    for source in sources:
        data = load_artifact(root / source['path'])
        for entry in data.get('original_layer_obligations', []):
            ids.add(entry['obligation_id'])
        for group in ('supplemental_boundary_requirements', 'interleaving_requirements', 'requirements'):
            for entry in data.get(group, []):
                name = entry.get('requirement_id', entry.get('id'))
                ids.update(name + '@' + layer for layer in entry['layers'])
    return ids


def hash_refresh_errors(root, base_revision, name, task, changed, protected_paths):
    """Only change hashes/byte counts of already-indexed, authorized changed files."""
    old = json.loads(git(root, 'show', base_revision + ':' + name))
    new = load_artifact(root / name)
    errors = []
    groups = ('documents', 'machine_readable') if name == INDEX else ('files',)
    old_meta = {k: v for k, v in old.items() if k not in groups}
    new_meta = {k: v for k, v in new.items() if k not in groups}
    if old_meta != new_meta:
        errors.append('derived-index-metadata:' + name)
    for group in groups:
        before, after = old.get(group, []), new.get(group, [])
        if [e['path'] for e in before] != [e['path'] for e in after]:
            errors.append('derived-index-paths:' + name)
            continue
        for previous, current in zip(before, after):
            if previous == current:
                continue
            path = previous['path']
            permitted = (path not in protected_paths and path in changed
                         and (matches(path, task['write_paths']) or (name == MANIFEST and path == INDEX)))
            if not permitted:
                errors.append('derived-index-unauthorized:' + path)
                continue
            if {k: v for k, v in previous.items() if k not in ('sha256', 'bytes')} != {k: v for k, v in current.items() if k not in ('sha256', 'bytes')}:
                errors.append('derived-index-entry:' + path)
            target = root / path
            if not target.is_file() or current.get('sha256') != sha(target):
                errors.append('derived-index-hash:' + path)
            if 'bytes' in current and (not target.is_file() or current['bytes'] != target.stat().st_size):
                errors.append('derived-index-bytes:' + path)
    return errors


def governance_index_errors(root, base_revision, record, changed, protected_paths):
    """Allow declared additions while preserving every existing authority identity."""
    old = json.loads(git(root, 'show', base_revision + ':' + INDEX))
    new = load_artifact(root / INDEX)
    errors = []
    if {k: v for k, v in old.items() if k not in ('documents', 'machine_readable')} != {
            k: v for k, v in new.items() if k not in ('documents', 'machine_readable')}:
        errors.append('governance-index-metadata')
    declared_additions = set(record.get('authority_entries_added', []))
    observed_additions = set()
    for group in ('documents', 'machine_readable'):
        before = {entry['path']: entry for entry in old.get(group, [])}
        after = {entry['path']: entry for entry in new.get(group, [])}
        removed = set(before) - set(after)
        if removed:
            errors.extend('governance-index-removal:' + path for path in sorted(removed))
        observed_additions |= set(after) - set(before)
        for path in sorted(set(before) & set(after)):
            previous, current = before[path], after[path]
            if previous == current:
                continue
            if path in protected_paths:
                errors.append('governance-index-frozen:' + path)
                continue
            if {k: v for k, v in previous.items() if k != 'sha256'} != {
                    k: v for k, v in current.items() if k != 'sha256'}:
                errors.append('governance-index-entry:' + path)
            target = root / path
            if path not in changed or not target.is_file() or current.get('sha256') != sha(target):
                errors.append('governance-index-hash:' + path)
        for path in sorted(set(after) - set(before)):
            current = after[path]
            target = root / path
            if path not in declared_additions:
                errors.append('governance-index-undeclared-addition:' + path)
            if path in protected_paths or not target.is_file() or current.get('sha256') != sha(target):
                errors.append('governance-index-addition-hash:' + path)
    if observed_additions != declared_additions:
        errors.append('governance-index-additions-mismatch')
    return errors


def task_index_authority_errors(root, base_revision, task, changed, protected_paths):
    """Permit a baseline-authorized index owner to add only files in its write scope."""
    old = json.loads(git(root, 'show', base_revision + ':' + INDEX))
    new = load_artifact(root / INDEX)
    errors = []
    if {k: v for k, v in old.items() if k not in ('documents', 'machine_readable')} != {
            k: v for k, v in new.items() if k not in ('documents', 'machine_readable')}:
        errors.append('authority-index-metadata')
    for group in ('documents', 'machine_readable'):
        before = {entry['path']: entry for entry in old.get(group, [])}
        after = {entry['path']: entry for entry in new.get(group, [])}
        for path in sorted(set(before) - set(after)):
            errors.append('authority-index-removal:' + path)
        for path, current in after.items():
            target = root / path
            if path in before:
                previous = before[path]
                if previous == current:
                    continue
                if path in protected_paths:
                    errors.append('authority-index-frozen:' + path)
                if {k: v for k, v in previous.items() if k != 'sha256'} != {
                        k: v for k, v in current.items() if k != 'sha256'}:
                    errors.append('authority-index-entry:' + path)
                if path not in changed or not matches(path, task['write_paths']):
                    errors.append('authority-index-unauthorized:' + path)
            elif path in protected_paths or not matches(path, task['write_paths']):
                errors.append('authority-index-addition:' + path)
            if (path not in before or before[path] != current) and (
                    not target.is_file() or current.get('sha256') != sha(target)):
                errors.append('authority-index-hash:' + path)
    return errors


def governance_manifest_errors(root, base_revision, changed):
    """The delivery manifest may refresh existing changed entries, never change its inventory."""
    old = json.loads(git(root, 'show', base_revision + ':' + MANIFEST))
    new = load_artifact(root / MANIFEST)
    errors = []
    if {k: v for k, v in old.items() if k != 'files'} != {k: v for k, v in new.items() if k != 'files'}:
        errors.append('governance-manifest-metadata')
    before, after = old.get('files', []), new.get('files', [])
    if [entry['path'] for entry in before] != [entry['path'] for entry in after]:
        errors.append('governance-manifest-paths')
        return errors
    for previous, current in zip(before, after):
        if previous == current:
            continue
        path = previous['path']
        if {k: v for k, v in previous.items() if k not in ('sha256', 'bytes')} != {
                k: v for k, v in current.items() if k not in ('sha256', 'bytes')}:
            errors.append('governance-manifest-entry:' + path)
        target = root / path
        if path not in changed or not target.is_file() or current.get('sha256') != sha(target):
            errors.append('governance-manifest-hash:' + path)
        if 'bytes' in current and (not target.is_file() or current['bytes'] != target.stat().st_size):
            errors.append('governance-manifest-bytes:' + path)
    return errors


def integration_record_errors(root, path, record, schema, result_schema, tasks):
    errors = ['integration-schema:' + path.name + ':' + issue.message
              for issue in schema.iter_errors(record)]
    if errors:
        return errors
    task_id = record['display_task_id']
    task = tasks.get(task_id)
    if not task or task['task_identity'] != record['task_identity'] or path.stem != task_id:
        return ['integration-identity:' + path.name]
    try:
        result_commit = resolve(root, record['result_commit'])
        reviewed = resolve(root, record['reviewed_head_sha'])
        review_commit = resolve(root, record['review_record_commit'])
        merge_commit = resolve(root, record['merge_commit'])
        head = resolve(root, 'HEAD')
        for before, after, label in (
                (result_commit, reviewed, 'result-to-reviewed'),
                (reviewed, review_commit, 'reviewed-to-review-record'),
                (review_commit, merge_commit, 'review-to-merge'),
                (merge_commit, head, 'merge-to-head')):
            try:
                git(root, 'merge-base', '--is-ancestor', before, after)
            except ValueError:
                errors.append('integration-ancestry:' + task_id + ':' + label)
        result_candidates = result_paths(task_id)
        result_paths_at_commit = [
            candidate for candidate in result_candidates
            if subprocess.run(
                ['git', 'cat-file', '-e', result_commit + ':' + candidate],
                cwd=root, capture_output=True).returncode == 0
        ]
        if len(result_paths_at_commit) != 1:
            errors.append(
                'integration-result-representation-count:' + task_id + ':'
                + str(len(result_paths_at_commit)))
        else:
            result_path = result_paths_at_commit[0]
            result = load_artifact_text(
                git(root, 'show', result_commit + ':' + result_path).decode(),
                Path(result_path).suffix)
            issues = list(result_schema.iter_errors(result))
            errors.extend('integration-result-schema:' + task_id + ':' + issue.message
                          for issue in issues)
            if (not issues and (
                    result.get('display_task_id') != task_id
                    or result.get('task_identity') != record['task_identity'])):
                errors.append('integration-result-identity:' + task_id)
        review_path = f'docs/exec-plans/reviews/{task_id}/GENERAL.json'
        review = json.loads(git(root, 'show', review_commit + ':' + review_path))
        if review.get('status') != 'PASS' or resolve(root, review.get('reviewed_head_sha', '')) != reviewed:
            errors.append('integration-review-binding:' + task_id)
    except ValueError as ex:
        errors.append('integration-revision:' + task_id + ':' + str(ex))
    return errors


def validate(root, args):
    from jsonschema import Draft202012Validator

    errors = []
    index, frozen, backlog = (load_artifact(root / n) for n in (INDEX, 'FROZEN_BASELINE.json', BACKLOG))
    for entry in index['documents'] + index.get('machine_readable', []) + frozen['files']:
        path = root / entry['path']
        if not relative_path(entry['path']) or not path.is_file():
            errors.append('missing:' + entry['path'])
        elif sha(path) != entry['sha256']:
            errors.append('hash:' + entry['path'])
    tasks = {task['id']: task for task in backlog['tasks']}
    identities = [t['task_identity'] for t in backlog['tasks']]
    if len(tasks) != len(backlog['tasks']) or len(identities) != len(set(identities)):
        errors.append('task-identity-duplicate')
    resource_text = (root / 'docs/harness/RESOURCE_LOCKS.md').read_text()
    known_resources = set(re.findall(r'^- `([^`]+)`$', resource_text, re.M))
    for task in backlog['tasks']:
        name = task['id']
        packet = root / 'docs/exec-plans/active' / (name + '.md')
        if packet.exists():
            errors.extend(packet_errors(task, packet.read_text()))
        elif task['status'] != 'SUPERSEDED':
            errors.append('packet:' + name)
        for dep in task['depends_on']:
            if dep not in tasks:
                errors.append('unknown-dep:' + name + '->' + dep)
        conditional_dependencies = task.get('conditional_depends_on', [])
        for conditional in conditional_dependencies:
            if isinstance(conditional, str):
                dep = conditional
            elif (isinstance(conditional, dict)
                  and isinstance(conditional.get('task_id'), str)
                  and isinstance(conditional.get('condition'), str)
                  and conditional['condition'].strip()):
                dep = conditional['task_id']
            else:
                errors.append('invalid-conditional-dep:' + name)
                continue
            if dep not in tasks:
                errors.append('unknown-conditional-dep:' + name + '->' + dep)
        resources = task.get('resource_keys', [])
        if len(resources) != len(set(resources)):
            errors.append('duplicate-resource-key:' + name)
        for resource in resources:
            if resource not in known_resources:
                errors.append('unknown-resource-key:' + name + '->' + resource)
        if task.get('status') == 'READY' and (task.get('packet_refinement') == 'MUST_REFINE_BEFORE_READY' or task.get('write_paths_status') != 'ENFORCEABLE'):
            errors.append('ready-write-scope-unrefined:' + name)
    pending = set(tasks)
    while pending:
        ready = set()
        for name in pending:
            conditional = tasks[name].get('conditional_depends_on', [])
            dependencies = set(tasks[name]['depends_on']) | {
                item if isinstance(item, str) else item.get('task_id') for item in conditional
            }
            if not dependencies & pending:
                ready.add(name)
        if not ready:
            errors.append('dag-cycle')
            break
        pending -= ready

    schemas = {}
    known_requirements = requirement_ids(root)
    schema_files = {
        'RESULT': 'THREAD_RESULT.schema.json',
        'REVIEW': 'THREAD_REVIEW.schema.json',
        'GOVERNANCE': GOVERNANCE_SCHEMA,
        'INTEGRATION': INTEGRATION_SCHEMA,
    }
    for kind, schema_name in schema_files.items():
        schema = load_artifact(root / schema_name)
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as ex:
            raise ValueError('invalid-schema:' + kind + ':' + str(ex)) from ex
        schemas[kind] = Draft202012Validator(schema)
    results = {}
    completed = root / 'docs/exec-plans/completed'
    for path in sorted(list(completed.glob('*_RESULT.yaml')) + list(completed.glob('*_RESULT.json'))):
        obj = load_artifact(path)
        issues = list(schemas['RESULT'].iter_errors(obj))
        if issues:
            errors.extend('result-schema:' + path.name + ':' + e.message for e in issues)
            continue
        task = tasks.get(obj['display_task_id'])
        if task is None:
            errors.append('result-unknown-task:' + path.name)
            continue
        if path.name not in [Path(p).name for p in result_paths(task['id'])] or task['id'] in results:
            errors.append('result-duplicate-or-path:' + path.name)
        results[task['id']] = (path, obj)
        errors.extend(path.name + ':' + e for e in semantic_result_errors(obj, task, root))
        requirement_names = [r['requirement_id'] for r in obj['requirements_covered']]
        if len(requirement_names) != len(set(requirement_names)):
            errors.append('result-duplicate-requirement:' + path.name)
        for requirement in obj['requirements_covered']:
            name = requirement['requirement_id']
            covered = task['requirements_covered']
            if name not in known_requirements or (name not in covered and name.split('@')[0] not in covered):
                errors.append('result-unknown-or-unassigned-requirement:' + name)

    reviews = []
    governance_reviews = []
    for path in sorted((root / 'docs/exec-plans/reviews').glob('*/*.json')):
        obj = load_artifact(path)
        issues = list(schemas['REVIEW'].iter_errors(obj))
        if issues:
            errors.extend('review-schema:' + path.name + ':' + e.message for e in issues)
            continue
        if re.fullmatch(r'HG-[0-9]{3}', path.parent.name):
            expected_identity = 'harness-governance-v0.1/' + path.parent.name
            if obj['task_identity'] != expected_identity or path.stem != obj['review_type']:
                errors.append('governance-review-identity-or-path:' + str(path.relative_to(root)))
                continue
            for ref in obj.get('evidence_refs', []):
                if not evidence_exists(root, ref):
                    errors.append('governance-review-evidence:' + ref)
            governance_reviews.append((path, obj))
            continue
        task = tasks.get(path.parent.name)
        if not task or task['task_identity'] != obj['task_identity'] or path.stem != obj['review_type']:
            errors.append('review-identity-or-path:' + str(path.relative_to(root)))
            continue
        for ref in obj.get('evidence_refs', []):
            if not evidence_exists(root, ref):
                errors.append('review-evidence:' + ref)
        reviews.append((path, obj, task))

    governance_records = {}
    governance_dir = root / 'docs/exec-plans/governance'
    if governance_dir.exists():
        for path in sorted(list(governance_dir.glob('HG-*.yaml')) +
                           list(governance_dir.glob('HG-*.json'))):
            record = load_artifact(path)
            issues = list(schemas['GOVERNANCE'].iter_errors(record))
            if issues:
                errors.extend('governance-schema:' + path.name + ':' + issue.message
                              for issue in issues)
                continue
            change_id = record['display_change_id']
            if path.stem != change_id or change_id in governance_records:
                errors.append('governance-duplicate-or-path:' + path.name)
            governance_records[change_id] = (path, record)
            if record['change_identity'] != 'harness-governance-v0.1/' + change_id:
                errors.append('governance-identity:' + change_id)
            check_ids = [check['check_id'] for check in record['checks_run']]
            if len(check_ids) != len(set(check_ids)):
                errors.append('governance-duplicate-check:' + change_id)
            for check in record['checks_run']:
                if check['result'] != 'PASS' or not evidence_exists(root, check['evidence_ref']):
                    errors.append('governance-check-evidence:' + change_id + ':' + check['check_id'])
            if record['change_status'] == 'PASS' and record['frozen_impact'] != 'NONE':
                errors.append('governance-pass-frozen-impact:' + change_id)

    integrations = root / 'docs/exec-plans/integrations'
    if integrations.exists():
        for path in sorted(integrations.glob('*.json')):
            record = load_artifact(path)
            errors.extend(integration_record_errors(
                root, path, record, schemas['INTEGRATION'], schemas['RESULT'], tasks))

    if (args.protected_base or args.reviewed_head or
            getattr(args, 'governance_reviewed_head', None)):
        # PR checks use committed artifacts and may not silently ignore working edits.
        if git(root, 'status', '--porcelain', '--untracked-files=all').strip():
            errors.append('git-worktree-not-clean')
    if args.protected_base:
        base_sha, head = resolve(root, args.protected_base), resolve(root, 'HEAD')
        git(root, 'merge-base', '--is-ancestor', base_sha, head)
        changed = set(changed_paths(root, base_sha, head))
        old_frozen = json.loads(git(root, 'show', base_sha + ':FROZEN_BASELINE.json'))
        protected_paths = {e['path'] for e in old_frozen['files']} | {'FROZEN_BASELINE.json'}
        errors.extend('protected-baseline-change:' + p for p in sorted(changed & protected_paths))
        if args.task_id:
            task = tasks.get(args.task_id)
            # The PR may not widen its own definition to authorize additional writes.
            old_tasks = json.loads(git(root, 'show', base_sha + ':' + BACKLOG))['tasks']
            baseline_task = next((t for t in old_tasks if t['id'] == args.task_id), None)
            if not task or not baseline_task or baseline_task.get('write_paths_status') != 'ENFORCEABLE':
                errors.append('write-scope-unrefined-or-unknown:' + args.task_id)
            else:
                allowed = baseline_task['write_paths'] + result_paths(args.task_id) + review_patterns(args.task_id) + [evidence_pattern(args.task_id)]
                for path in sorted(changed):
                    if (path == INDEX and
                            INDEX in baseline_task.get('authority_update_paths', [])):
                        errors.extend(task_index_authority_errors(
                            root, base_sha, baseline_task, changed, protected_paths))
                    elif path in (INDEX, MANIFEST):
                        errors.extend(hash_refresh_errors(root, base_sha, path, baseline_task, changed, protected_paths))
                    elif not matches(path, allowed):
                        errors.append('write-scope:' + args.task_id + ':' + path)
        elif getattr(args, 'governance_change_id', None):
            change_id = args.governance_change_id
            selected = governance_records.get(change_id)
            if not selected:
                errors.append('governance-record-missing:' + change_id)
            else:
                _, record = selected
                if record['change_status'] != 'PASS':
                    errors.append('governance-change-not-pass:' + change_id)
                if resolve(root, record['base_commit']) != base_sha:
                    errors.append('governance-base-mismatch:' + change_id)
                for path in sorted(changed):
                    if not matches(path, governance_allowed_patterns(change_id)):
                        errors.append('governance-write-scope:' + change_id + ':' + path)
                reviewed = resolve(root, args.governance_reviewed_head)
                declared = set(record['files_changed'])
                actual_at_review = set(changed_paths(root, base_sha, reviewed))
                if declared != actual_at_review:
                    errors.append('governance-files-changed-mismatch:' + change_id)
                errors.extend(governance_index_errors(
                    root, base_sha, record, changed, protected_paths))
                errors.extend(governance_manifest_errors(root, base_sha, changed))

                old_tasks = {task['id']: task for task in
                             json.loads(git(root, 'show', base_sha + ':' + BACKLOG))['tasks']}
                changed_task_ids = {
                    task_id for task_id in set(old_tasks) | set(tasks)
                    if old_tasks.get(task_id) != tasks.get(task_id)
                }
                args.governance_changed_task_ids = changed_task_ids
                args.governance_base_tasks = old_tasks
                refined = set(record['packets_refined'])
                observed = set()
                for task_id in refined:
                    task = tasks.get(task_id)
                    old_task = old_tasks.get(task_id)
                    if not task or not old_task:
                        errors.append('governance-refined-task-unknown:' + task_id)
                        continue
                    if (old_task.get('packet_refinement') == 'MUST_REFINE_BEFORE_READY' and
                            task.get('packet_refinement') != 'MUST_REFINE_BEFORE_READY'):
                        observed.add(task_id)
                    if (task.get('write_paths_status') != 'ENFORCEABLE' or
                            not task.get('write_paths') or
                            any('TO_BE_REFINED' in path for path in task.get('write_paths', []))):
                        errors.append('governance-refinement-incomplete:' + task_id)
                changed_packets = {
                    Path(path).stem for path in changed
                    if re.fullmatch(r'docs/exec-plans/active/KL-[0-9]{3}[A-Z]?\.md', path)
                }
                if refined != observed or refined != changed_packets:
                    errors.append('governance-refined-packets-mismatch:' + change_id)
        else:
            errors.append('protected-change-kind-required')

    for path, review, task in reviews:
        # Historical reviews describe their own PR, not every later repository HEAD.
        if review['status'] != 'PASS' or not args.reviewed_head or task['id'] != args.task_id:
            continue
        reviewed = review['reviewed_head_sha']
        errors.extend(suffix_errors(root, reviewed, 'HEAD', task['id'], 'review'))
        result = results.get(task['id'])
        if not result:
            errors.append('review-missing-result:' + task['id'])
            continue
        result_path, obj = result
        try:
            if git(root, 'show', resolve(root, reviewed) + ':' + str(result_path.relative_to(root))) != result_path.read_bytes():
                errors.append('review-result-not-bound:' + task['id'])
            if obj['task_status'] != 'PASS':
                errors.append('review-result-not-pass:' + task['id'])
            git(root, 'merge-base', '--is-ancestor', resolve(root, obj['base_commit']), resolve(root, obj['tested_commit']))
            errors.extend(suffix_errors(root, obj['tested_commit'], reviewed, task['id'], 'tested'))
            refs = [c.get('evidence_ref') for c in obj['commands_run']] + [r.get('evidence_ref') for r in obj['requirements_covered']]
            for ref in filter(None, refs):
                if git(root, 'show', resolve(root, reviewed) + ':' + ref) != (root / ref).read_bytes():
                    errors.append('review-evidence-not-bound:' + ref)
        except ValueError as ex:
            errors.append('review-revision:' + str(ex))
    if args.reviewed_head:
        if not args.task_id:
            errors.append('review-suffix:task-id-required')
        else:
            errors.extend(suffix_errors(root, args.reviewed_head, 'HEAD', args.task_id, 'review'))
            task = tasks.get(args.task_id)
            relevant = [review for _, review, t in reviews if t['id'] == args.task_id and review['status'] == 'PASS']
            types = {r['review_type'] for r in relevant if resolve(root, r['reviewed_head_sha']) == resolve(root, args.reviewed_head)}
            if not task or not set(task['review_requirements']) <= types:
                errors.append('required-reviews-not-pass:' + args.task_id)
    if getattr(args, 'governance_reviewed_head', None):
        change_id = args.governance_change_id
        reviewed = resolve(root, args.governance_reviewed_head)
        errors.extend(governance_suffix_errors(root, reviewed, 'HEAD', change_id, 'review'))
        selected = governance_records.get(change_id)
        if not selected:
            errors.append('governance-record-missing:' + change_id)
        else:
            record_path, record = selected
            try:
                if git(root, 'show', reviewed + ':' + str(record_path.relative_to(root))) != record_path.read_bytes():
                    errors.append('governance-record-not-bound:' + change_id)
                git(root, 'merge-base', '--is-ancestor',
                    resolve(root, record['base_commit']), resolve(root, record['tested_commit']))
                errors.extend(governance_suffix_errors(
                    root, record['tested_commit'], reviewed, change_id, 'tested'))
                for check in record['checks_run']:
                    ref = check['evidence_ref']
                    if git(root, 'show', reviewed + ':' + ref) != (root / ref).read_bytes():
                        errors.append('governance-evidence-not-bound:' + ref)
            except ValueError as ex:
                errors.append('governance-review-revision:' + str(ex))
            required = {'GENERAL'}
            old_tasks = getattr(args, 'governance_base_tasks', {})
            changed_task_ids = getattr(args, 'governance_changed_task_ids', set())
            for task_id in changed_task_ids:
                required.update(old_tasks.get(task_id, {}).get('review_requirements', []))
                required.update(tasks.get(task_id, {}).get('review_requirements', []))
            types = {
                review['review_type'] for _, review in governance_reviews
                if review['status'] == 'PASS' and
                resolve(root, review['reviewed_head_sha']) == reviewed
            }
            if not required <= types:
                errors.append('governance-required-reviews-not-pass:' + change_id)
    return errors, len(tasks), sum(t['status'] != 'SUPERSEDED' for t in tasks.values())


def main(argv=None, root=ROOT):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protected-base', help='Trusted, already-integrated base commit for PR protection.')
    parser.add_argument('--reviewed-head', help='Reviewed implementation/result revision; requires --task-id.')
    parser.add_argument('--task-id')
    parser.add_argument('--ci-pr-base', help='Pull request base SHA supplied by CI.')
    parser.add_argument('--ci-pr-head', help='Pull request head SHA supplied by CI.')
    parser.set_defaults(governance_change_id=None, governance_reviewed_head=None)
    args = parser.parse_args(argv)
    try:
        if args.ci_pr_base or args.ci_pr_head:
            configure_ci_merge_gate(root, args)
        errors, count, active = validate(root, args)
    except (ValueError, KeyError, TypeError, OSError, ImportError) as ex:
        errors, count, active = ['validation-error:' + str(ex)], 0, 0
    if errors:
        print('HARNESS_CHECK_FAIL')
        print('\n'.join(errors))
        return 1
    print(f'HARNESS_CHECK_PASS tasks={count} active={active}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
