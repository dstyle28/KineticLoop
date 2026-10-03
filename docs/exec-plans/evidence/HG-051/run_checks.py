"""Run real required HG051 checks at one clean committed source, outputs outside tree."""
from __future__ import annotations

import concurrent.futures
import json
import os
import shlex
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BASE = 'b877db0edd2e4550d6ea81750656112fb7f2e223'


def main():
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT)
    out = Path('/private/tmp/hg051-checks-' + sha[:7])
    out.mkdir(exist_ok=False)
    env = dict(os.environ)
    env['PATH'] = '/private/tmp/hg048-tools/bin:' + str(ROOT / '.venv/bin') + ':' + env['PATH']
    env['UV_CACHE_DIR'] = '/private/tmp/hg050-uv-cache'
    commands = {
        'focused': 'uv run pytest -q tests/harness/test_compact_evidence.py tests/harness/test_source_decision_scope.py tests/harness/test_review_evidence_provenance.py tests/harness/test_m3_milestone_closure.py tests/harness/test_validator.py -k 'archiv or hg051 or source_decision_scope or manifest_tamper or bounded_single_member or decoded_reserved or exact_retrieval' -n 2 --junitxml=' + str(out / 'focused.xml') + ' --basetemp=' + str(out / 'focused-temp'),
        'harness': 'uv run kl test-harness --workers 2 --evidence-dir ' + str(out / 'harness') + ' -q --basetemp=' + str(out / 'harness-temp'),
        'unit': 'uv run kl test-unit -q --junitxml=' + str(out / 'unit.xml'),
        'authority': 'uv run kl check-harness',
        'lint': 'uv run kl lint',
        'typecheck': 'uv run kl typecheck',
        'scope_frozen_prerequisites': 'uv run python docs/exec-plans/evidence/HG-051/scope_audit.py',
        'inventory_roundtrip': 'uv run python docs/exec-plans/evidence/HG-051/inventory_roundtrip.py',
        'diff': 'git diff --check ' + BASE + ' ' + sha,
        'budget': 'uv run python tools/harness/compact_evidence.py audit --base ' + BASE + ' --head ' + sha + ' --identity HG-051',
    }

    def run(item):
        name, command = item
        start = time.time()
        with (out / (name + '.log')).open('wb') as log:
            result = subprocess.run(shlex.split(command), cwd=ROOT, env=env, stdout=log,
                                    stderr=subprocess.STDOUT)
        record = dict(check_id=name, command=command, exit_code=result.returncode,
                      tested_commit=sha, elapsed_seconds=time.time() - start,
                      log=str(out / (name + '.log')))
        print(json.dumps(record), flush=True)
        return record

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(run, commands.items()))
    final_sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    final_status = subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True)
    report = dict(tested_commit=sha, source_end_sha=final_sha,
                  source_end_status=final_status, executions=records)
    (out / 'EXECUTION.json').write_text(json.dumps(report, indent=2) + '\n')
    assert sha == final_sha and not final_status
    raise SystemExit(any(r['exit_code'] for r in records))


if __name__ == '__main__':
    main()
