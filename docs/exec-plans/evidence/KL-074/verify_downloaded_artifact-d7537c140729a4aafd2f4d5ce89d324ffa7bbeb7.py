import base64
import hashlib
import importlib.util
import json
import os
import re
import zipfile
from pathlib import Path

ROOT = Path.cwd().resolve()
SHA = 'd7537c140729a4aafd2f4d5ce89d324ffa7bbeb7'
RUN_ID = 36819284887
PREFIX = Path('/private/tmp')

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def read_json(path):
    return json.loads(path.read_text())

run = read_json(PREFIX / f'kl074-run-{RUN_ID}.json')
artifacts = read_json(PREFIX / f'kl074-artifacts-{RUN_ID}.json')['artifacts']
jobs = read_json(PREFIX / f'kl074-jobs-{RUN_ID}.json')['jobs']
assert run['id'] == RUN_ID and run['head_sha'] == SHA and run['event'] == 'pull_request'
assert run['conclusion'] == 'success' and run['status'] == 'completed' and run['run_attempt'] == 1
assert run['head_branch'] == 'codex/kl074-postgres-readiness'
assert run['head_repository']['id'] == run['repository']['id'] == 1377771702
assert run['path'] == '.github/workflows/kl074-readiness.yml'
assert any(pr['number'] == 72 for pr in run['pull_requests'])
assert len(jobs) == 1 and jobs[0]['name'] == 'kl074-readiness' and jobs[0]['conclusion'] == 'success'
assert jobs[0]['head_sha'] == SHA and jobs[0]['labels'] == ['ubuntu-latest']
for name in ('Exact revision and dedicated local-daemon preflight', 'Bounded owned migrated coldstarts', 'Exact complete repository regression', 'Preserve exact-head success and failure evidence'):
    assert next(step for step in jobs[0]['steps'] if step['name'] == name)['conclusion'] == 'success'
assert len(artifacts) == 1
artifact = artifacts[0]
assert artifact['name'] == f'kl074-readiness-{SHA}-{RUN_ID}-1' and not artifact['expired']
assert artifact['workflow_run']['head_sha'] == SHA and artifact['workflow_run']['id'] == RUN_ID
assert artifact['workflow_run']['repository_id'] == artifact['workflow_run']['head_repository_id'] == 1377771702
archive_path = PREFIX / f"kl074-artifact-{artifact['id']}.zip"
archive = archive_path.read_bytes()
assert 'sha256:' + digest(archive) == artifact['digest'] and len(archive) == artifact['size_in_bytes']
with zipfile.ZipFile(archive_path) as opened:
    names = [name for name in opened.namelist() if not name.endswith('/')]
    assert len(names) == len(set(names))
    assert all(not Path(name).is_absolute() and '..' not in Path(name).parts for name in names)
    files = {name: opened.read(name) for name in names}

def artifact_json(name):
    return json.loads(files[name])

provenance = artifact_json('hosted-provenance.json')
assert provenance['tested_commit'] == SHA and provenance['run_id'] == str(RUN_ID) and provenance['run_attempt'] == '1'
assert provenance['runner_environment'] == 'github-hosted' and provenance['runner_os'] == 'Linux'
assert provenance['docker_context'] == 'default' and provenance['docker_endpoint'] == 'unix:///var/run/docker.sock'
assert provenance['coldstart_command'] == 'uv run python tools/db/verify_startup_readiness.py --iterations 3 --startup-timeout 60 --total-timeout 300'
assert provenance['full_repository_command'] == 'uv run pytest -q -p no:cacheprovider'
summary = artifact_json('coldstart-summary.json')
assert summary['status'] == 'PASS' and summary['tested_commit'] == SHA and summary['cross_root_separation']
assert 0 < summary['elapsed_seconds'] < 300 and len(summary['iterations']) == 3
assert len({item['project_name'] for item in summary['iterations']}) == 3
assert len({item['database_name'] for item in summary['iterations']}) == 3
spec = importlib.util.spec_from_file_location('kl074_download_probe', ROOT / 'tools/db/verify_startup_readiness.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
identities = []
for iteration in range(1, 4):
    path = f'iteration-{iteration}/'
    before = artifact_json(path + 'ownership-before.json')
    assertions = artifact_json(path + 'assertions.json')
    cleanup = artifact_json(path + 'cleanup.json')
    image = artifact_json(path + 'image-provenance.json')
    topology = artifact_json(path + 'actual-topology.json')
    observer = artifact_json(path + 'socket-tcp-observer.json')
    events = [json.loads(line) for line in files[path + 'events.jsonl'].decode().splitlines()]
    root = before['root']
    assert root.startswith('/tmp/kineticloop-kl074-cold-') and root.endswith('/KineticLoop')
    physical_digest = digest(os.fsencode(root))[:12]
    project = f'kineticloop-kl074-cold-{SHA[:7]}-{physical_digest}'
    database = f"kineticloop_kl074_cold_{SHA[:7]}_{physical_digest}"
    assert before['tested_commit'] == assertions['tested_commit'] == SHA
    assert before['project_name'] == assertions['project_name'] == cleanup['project_name'] == project
    assert before['database_name'] == assertions['database_name'] == database
    assert before['root'] == assertions['root']
    assert before['compose_sha256'] == digest((ROOT / 'compose.yaml').read_bytes())
    assert all(values == [] for values in before['preexisting_resources'].values())
    assert assertions['status'] == 'PASS' and assertions['sentinel_removed'] and assertions['current_database_verified_twice']
    assert assertions['migrated_revision'] == assertions['expected_revision'] == 'e8c2f1a6b904'
    assert assertions['exact_owned_drop_count'] == assertions['exact_owned_create_count'] == 3
    assert cleanup['status'] == 'PASS' and cleanup['errors'] == []
    assert all(values == [] for values in cleanup['remaining_resources'].values())
    assert image['configured_image'] == 'postgres:16.10-alpine'
    assert image['resolved_image']['id'].startswith('sha256:') and image['resolved_image']['digests']
    assert image['resolved_image']['entrypoint'] == ['docker-entrypoint.sh']
    assert digest(files[path + 'docker-entrypoint.sh.txt']) == image['entrypoint_sha256']
    identities.append((image['resolved_image']['id'], tuple(image['resolved_image']['digests']), image['entrypoint_sha256']))
    assert topology['project'] == project and set(topology['networks']) == {f'{project}_default'}
    assert any(mount.get('Name') == f'{project}_postgres-data' and mount['Destination'] == '/var/lib/postgresql/data' for mount in topology['mounts'])
    raw = artifact_json(path + 'container-raw-log.json')
    assert digest(raw['stdout'].encode()) == raw['stdout_sha256'] and digest(raw['stderr'].encode()) == raw['stderr_sha256']
    logs = '\n'.join(sorted((raw['stdout'] + raw['stderr']).splitlines())) + '\n'
    assert logs.encode() == files[path + 'container.log']
    assert observer['returncode'] == 0 and digest(observer['stdout'].encode()) == observer['stdout_sha256']
    assert probe.verify_ordering(logs, events, observer['stdout']) == artifact_json(path + 'ordering.json')
    sql = [event['command'] for event in events if event['kind'] == 'sql_begin']
    assert all(command[command.index('--dbname') + 1] in (database, 'postgres') and '--host' not in command and '--port' not in command for command in sql)
    assert sum(command[-1] == f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE);' for command in sql) == 3
    assert sum(command[-1] == f'CREATE DATABASE "{database}" OWNER "<redacted>";' for command in sql) == 3
    for event in events:
        if event['kind'] != 'tcp_probe_begin':
            continue
        command = event['command']
        assert command[command.index('--project-name') + 1] == project
        assert command[command.index('--file') + 1] == root + '/compose.yaml'
        assert command[command.index('--host') + 1] == '127.0.0.1'
        assert command[command.index('--port') + 1] == '5432'
        assert 0 < event['requested_timeout'] <= 60
    current_database_results = [event['stdout'].strip() for i, event in enumerate(events) if event['kind'] == 'sql_end' and events[i - 1]['kind'] == 'sql_begin' and events[i - 1]['command'][-1] == 'SELECT current_database();']
    assert current_database_results == [database, database]
assert len(set(identities)) == 1
full = files['full-repository.log'].decode()
assert full.splitlines()[0] == 'tested_commit=' + SHA
assert not re.search(r'\b\d+ (?:failed|skipped|xfailed|xpassed|errors?)\b', full)
passes = re.search(r'(\d+) passed(?:, \d+ warnings?)? in ([0-9.]+)s', full)
assert passes and int(passes.group(1)) > 440
assert files['coldstart.log'].decode().splitlines()[0] == 'tested_commit=' + SHA
out = ROOT / 'docs/exec-plans/evidence/KL-074' / f'hosted-{SHA}'
assert not out.exists()
out.mkdir()
manifest = {}
def preserve(raw, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    value = {'raw_sha256': digest(raw), 'raw_byte_count': len(raw)}
    try:
        value['raw_utf8'] = raw.decode()
    except UnicodeDecodeError:
        value['raw_base64'] = base64.b64encode(raw).decode()
    target.write_text(json.dumps(value, indent=2) + '\n')
    return {key: value[key] for key in ('raw_sha256', 'raw_byte_count')}
for name, raw in files.items():
    manifest[name] = preserve(raw, out / 'artifact' / (name + '.envelope.json'))
for name, source in [('run', PREFIX / f'kl074-run-{RUN_ID}.json'), ('jobs', PREFIX / f'kl074-jobs-{RUN_ID}.json'), ('artifact-metadata', PREFIX / f'kl074-artifacts-{RUN_ID}.json'), ('archive', archive_path), ('run-log', PREFIX / f'kl074-log-{RUN_ID}.txt')]:
    preserve(source.read_bytes(), out / (name + '.envelope.json'))
verified = {'status': 'PASS', 'tested_commit': SHA, 'run_id': RUN_ID, 'run_attempt': 1, 'event': run['event'], 'run_url': run['html_url'], 'job_id': jobs[0]['id'], 'job_url': jobs[0]['html_url'], 'artifact_id': artifact['id'], 'artifact_digest': artifact['digest'], 'downloaded_archive_sha256': digest(archive), 'full_repository_pass_count': int(passes.group(1)), 'full_repository_seconds': float(passes.group(2)), 'coldstart_elapsed_seconds': summary['elapsed_seconds'], 'identical_actual_image_and_entrypoint': identities[0], 'raw_files': manifest, 'commands': [provenance['coldstart_command'], provenance['full_repository_command']]}
(out / 'VERIFIED.json').write_text(json.dumps(verified, indent=2) + '\n')
print(json.dumps({key: value for key, value in verified.items() if key != 'raw_files'}, indent=2))
