"""Bounded independent pure/Git checks; no PostgreSQL lifecycle."""
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[5]
out = Path(__file__).parent
python = '/private/tmp/hg044-venv/bin/python'
reviewed = '19dc5a4f8edc8869873a76a4fe27b0280761d7c9'
env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(root / 'src'))
temp = tempfile.mkdtemp(prefix='hg044-protocol-r3-', dir='/private/tmp')
commands = [
    [python, str(out / 'audit.py')],
    [python, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '--basetemp=' + temp,
     'tests/harness/test_m3_milestone_closure.py', '-k',
     'prospective_full_git_chain or each_multiselect_suite or float_exit or '
     'existing_schema_branches or actual_closure_record or zero_skip_xfail or '
     'governance_scope or ratified_plan or reader_parses or symlink_is_rejected'],
    ['git', 'diff', '--check', 'fa729ca4bcca0f2c2e7a2aa0601890d1356b8842', reviewed],
]
records = []
for index, command in enumerate(commands):
    process = subprocess.run(command, cwd=root, env=env, capture_output=True)
    raw = process.stdout + process.stderr
    path = out / f'command-{index}.log'
    path.write_bytes(raw)
    records.append({'argv': command, 'reviewed_head_sha': reviewed,
                    'exit_code': process.returncode, 'raw_path': str(path.relative_to(root)),
                    'raw_sha256': hashlib.sha256(raw).hexdigest(), 'raw_byte_count': len(raw)})
    print(json.dumps({'command_index': index, 'exit_code': process.returncode}), flush=True)
    if process.returncode:
        break
(out / 'commands.json').write_text(json.dumps({'reviewed_head_sha': reviewed,
    'temp_namespace': temp, 'no_database_lifecycle': True, 'commands': records}, indent=2) + '\n')
raise SystemExit(0 if len(records) == len(commands) and all(r['exit_code'] == 0 for r in records) else 1)
