"""Synthetic validator inputs only; never product or release evidence."""
import copy
import importlib.util
import tempfile
from pathlib import Path
root = Path('/Users/davetian/.codex/worktrees/ffff/KineticLoop')
spec = importlib.util.spec_from_file_location('m3_fixture', root / 'tests/harness/test_m3_milestone_closure.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
v = fixture.v
with tempfile.TemporaryDirectory(prefix='hg046-protocol-repro-') as directory:
    history = fixture.History(Path(directory) / 'repo')
    payload = copy.deepcopy(history.payload)
    print('clean_regression_errors:', v.m3_execution_evidence_errors(history.root, payload, history.evaluated, history.evaluated, history.records))
    run = payload['executions'][0]
    ref = history.prefix + 'invalid-payload.json'
    manifest = v.compact_evidence.capture(history.root, ref, b'1 skipped\n', history.tested, run['command'], 0, '1 passed')
    (history.root / manifest['payload']).unlink()
    run['stdout'] = {'path': ref, 'sha256': v.sha(history.root / ref)}
    json_revision = history.commit('synthetic missing compact payload')
    print('json_missing_payload_errors:', v.m3_execution_evidence_errors(history.root, payload, json_revision, json_revision, history.records))
    log_ref = ref.removesuffix('.json') + '.log'
    (history.root / log_ref).write_bytes((history.root / ref).read_bytes())
    run['stdout'] = {'path': log_ref, 'sha256': v.sha(history.root / log_ref)}
    log_revision = history.commit('synthetic renamed compact envelope')
    print('renamed_log_missing_payload_evidence_exists:', v.evidence_exists(history.root, log_ref, log_revision, history.tested, run['command'], 0))
    print('renamed_log_missing_payload_regression_errors:', v.m3_execution_evidence_errors(history.root, payload, log_revision, log_revision, history.records))
    print('renamed_log_budget_errors:', v.compact_evidence.audit(history.root, history.tested, log_revision, 'HG-999')['errors'])
    print('expected: invalid/missing compact payload must fail regardless of reference extension; timestamp metadata cannot replace raw execution counts')
