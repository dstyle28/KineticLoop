"""Read-only audit of the KL025 entry blocker; creates no DB resources."""
from pathlib import Path
import hashlib
import json
import subprocess
ROOT = Path(__file__).resolve().parents[4]
BASE = 'd93131d'
records = []
for file, needles in {
    'tests/db/test_safety_registry.py': ['kineticloop-kl021-ec264bb', 'kineticloop_kl021_ec264bb'],
    'tests/db/test_factsets.py': ['kineticloop-kl023-{shortsha}', 'kineticloop_kl023_{shortsha}'],
}.items():
    data = subprocess.check_output(['git', 'show', f'{BASE}:{file}'], cwd=ROOT)
    source = data.decode()
    assert all(n in source for n in needles)
    fixture = source[source.index('def database_urls('):]
    fixture = fixture[:fixture.index('\n\ndef ') if '\n\ndef ' in fixture else len(fixture)]
    assert 'os.environ' not in fixture and 'FIXTURE_OWNER' not in fixture
    records.append({'path': file, 'sha256': hashlib.sha256(data).hexdigest(),
                    'namespace': needles, 'supported_task_selector': False,
                    'fixture_source': fixture})
print(json.dumps({'base_commit': subprocess.check_output(['git', 'rev-parse', BASE], cwd=ROOT, text=True).strip(),
 'status': 'MUST_REFINE_BEFORE_READY', 'db_or_docker_commands_run': False,
 'requested_regression': 'uv run pytest tests/db',
 'ci_source': '.github/workflows/db.yml', 'foreign_namespace_fixtures': records,
 'packet_scope': 'Only HG034 exact tests/db/test_planning.py patch is permitted; never reset another task database.'}, indent=2))
