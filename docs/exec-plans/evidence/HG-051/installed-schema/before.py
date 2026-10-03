import importlib.util, json, pathlib, shutil, subprocess, traceback
source = pathlib.Path('/Users/davetian/.codex/worktrees/83f7/KineticLoop')
output = pathlib.Path('/private/tmp/hg051-installed-schema-preflight')
installed = output / 'gate/tools/harness'
installed.mkdir(parents=True, exist_ok=True)
for asset in ('validate_harness.py', 'compact_evidence.py', 'db_ci_pytest.py', 'db_ci.py', 'gate_validate.py', 'gate_pytest.py'):
    shutil.copyfile(source / 'tools/harness' / asset, installed / asset)
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
repo_ce = load('repo_ce', source / 'tools/harness/compact_evidence.py')
gate_ce = load('gate_ce', installed / 'compact_evidence.py')
report = {'head': repo_ce.git(source, 'rev-parse', 'HEAD').decode().strip(), 'installed_files': sorted(p.name for p in installed.iterdir()), 'expected_schema': str(installed.parents[1] / repo_ce.MAPPING_SCHEMA)}
def record(name, fn):
    try:
        report[name] = {'success': True, 'result': fn()}
    except Exception as exc:
        report[name] = {'success': False, 'error': repr(exc), 'traceback': traceback.format_exc()}
record('repository_schema_original_count', lambda: len(repo_ce.historical_originals()))
record('installed_schema_original_count', lambda: len(gate_ce.historical_originals()))
record('installed_no_archives_audit', lambda: [list(x) for x in gate_ce.archive_audit(source, report['head'])])
record('installed_HG051_budget', lambda: gate_ce.audit(source, 'b877db0edd2e4550d6ea81750656112fb7f2e223', report['head'], 'HG-051'))
record('installed_KL080_budget_before_migration', lambda: gate_ce.audit(source, 'b877db0edd2e4550d6ea81750656112fb7f2e223', report['head'], 'KL-080'))
# Store the actual four approved byte sequences in a temporary archive-only Git repository.
fixture = output / 'archive-fixture'
fixture.mkdir(exist_ok=True)
repo_ce.git(fixture, 'init', '-q')
repo_ce.git(fixture, 'config', 'user.email', 'fixture@example.invalid')
repo_ce.git(fixture, 'config', 'user.name', 'Fixture')
originals = repo_ce.historical_originals()
raw_sizes = []
for original in originals:
    raw = repo_ce.archive_original(source, original)
    manifest, stored = repo_ce.archive_envelope(original, raw)
    raw_sizes.append(len(raw))
    dest = fixture / original['path']
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(manifest))
    (fixture / manifest['payload']).write_bytes(stored)
repo_ce.git(fixture, 'add', '.')
repo_ce.git(fixture, 'commit', '-qm', 'Temporary storage fixture')
revision = repo_ce.git(fixture, 'rev-parse', 'HEAD').decode().strip()
mapping = repo_ce.historical_template()
mapping['entries'] = []
for original in originals:
    data = repo_ce.blob(fixture, original['path'], revision)
    manifest = repo_ce.envelope(data)
    mapping['entries'].append({'original': original, 'storage': {'revision': revision, 'envelope_path': original['path'], 'envelope_sha256': repo_ce.digest(data), 'envelope_bytes': len(data), 'payload': manifest['payload'], 'payload_sha256': manifest['stored_sha256'], 'payload_bytes': manifest['stored_bytes']}})
(fixture / repo_ce.MAPPING_PATH).write_text(json.dumps(mapping))
repo_ce.git(fixture, 'add', '.')
repo_ce.git(fixture, 'commit', '-qm', 'Temporary mapping fixture')
head = repo_ce.git(fixture, 'rev-parse', 'HEAD').decode().strip()
report['fixture'] = {'path': str(fixture), 'head': head, 'raw_sizes': raw_sizes, 'original_proof_claim': False}
record('repository_approved_archive_retrieval', lambda: {p: len(raw) for p, raw in repo_ce.validate_archive(fixture, mapping, head).items()})
record('installed_approved_archive_retrieval', lambda: {p: len(raw) for p, raw in gate_ce.validate_archive(fixture, mapping, head).items()})
(output / 'REPORT.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k: {a: b for a, b in v.items() if a != 'traceback'} if isinstance(v, dict) else v for k, v in report.items()}, indent=2))
