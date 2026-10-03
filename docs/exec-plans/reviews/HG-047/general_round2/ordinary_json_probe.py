"""Reproduce nonreserved duplicate-key JSON rejection without candidate writes."""
import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path

root = Path('/Users/davetian/.codex/worktrees/ffff/KineticLoop')
spec = importlib.util.spec_from_file_location('ce', root / 'tools/harness/compact_evidence.py')
ce = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ce)
report = {'reviewed_head': 'b7370940c8b9165f471322baaeef7d9e250dfac6',
          'classification': 'NONBLOCKING', 'finding_id': 'G-01', 'cases': []}
with tempfile.TemporaryDirectory(prefix='hg047-general-plain-') as dirname:
    repo = Path(dirname)
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=repo).decode().strip()
    git('init', '-q')
    git('config', 'user.name', 'Review fixture')
    git('config', 'user.email', 'fixture@example.invalid')
    directory = repo / 'docs/exec-plans/evidence/HG-047'
    directory.mkdir(parents=True)
    samples = [('literal', b'{"event":"a","x":1,"x":2}'),
               ('escaped', b'{"event":"\\u0061","x":1,"x":2}')]
    for name, data in samples:
        (directory / (name + '.log')).write_bytes(data)
    git('add', '.')
    git('commit', '-qm', 'isolated ordinary JSON proof')
    sha = git('rev-parse', 'HEAD')
    for name, data in samples:
        ref = 'docs/exec-plans/evidence/HG-047/' + name + '.log'
        try:
            recovered = ce.read(repo, ref, sha)
            assert recovered == data
            observed = 'byte_identical'
        except ValueError as error:
            observed = str(error)
        assert observed == ('byte_identical' if name == 'literal' else 'evidence-duplicate-key')
        report['cases'].append({'case': name, 'sample': data.decode(), 'observed': observed})
print(json.dumps(report, indent=2))
