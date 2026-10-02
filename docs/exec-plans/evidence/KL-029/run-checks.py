"""Run exactly the twelve packet checks on one immutable tested implementation SHA."""
import hashlib
import json
import os
import re
import shlex
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path

root = Path(__file__).resolve().parents[4]
packet = (root / 'docs/exec-plans/active/KL-029.md').read_text()
contracts = json.loads(re.search(r'```json\n(.*?)\n```', packet, re.S).group(1))['check_contracts']
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
directory = Path(__file__).resolve().parent / ('checks-' + head[:7])
directory.mkdir(exist_ok=True)
records = []
for item in contracts:
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip() == head
    check = item['check_id']
    log = directory / (check + '.log')
    xml = directory / (check + '.xml')
    env = dict(os.environ)
    env['PYTEST_ADDOPTS'] = '-rA --junitxml=' + str(xml)
    started = time.monotonic()
    with log.open('w') as output:
        output.write(json.dumps({'tested_commit': head, 'command': item['command'], 'resolved_root': str(root), 'oracle': item['pass_oracle'], 'pytest_addopts': env['PYTEST_ADDOPTS']}) + '\n')
        output.flush()
        completed = subprocess.run(shlex.split(item['command']), cwd=root, env=env, stdout=output, stderr=subprocess.STDOUT, timeout=900)
    stats = None
    if xml.exists():
        suites = list(ET.parse(xml).getroot().iter('testsuite'))
        stats = {key: sum(int(s.get(key, '0')) for s in suites) for key in ('tests', 'failures', 'errors', 'skipped')}
        assert stats['tests'] > 0 and stats['skipped'] == 0, stats
    passed = completed.returncode == 0 and (stats is None or not stats['failures'] and not stats['errors'])
    records.append({'check_id': check, 'command': item['command'], 'result': 'PASS' if passed else 'FAIL', 'exit_code': completed.returncode, 'evidence_ref': str(log.relative_to(root)), 'log_sha256': hashlib.sha256(log.read_bytes()).hexdigest(), 'junit_ref': str(xml.relative_to(root)) if xml.exists() else None, 'counts': stats, 'elapsed_seconds': time.monotonic() - started})
    (directory / 'checks.json').write_text(json.dumps({'tested_commit': head, 'root': str(root), 'compose': 'kineticloop-kl029-shadow-'+head[:7]+'-'+hashlib.sha256(os.fsencode(root)).hexdigest()[:12], 'database': 'kineticloop_kl029_shadow_'+head[:7]+'_'+hashlib.sha256(os.fsencode(root)).hexdigest()[:12], 'checks': records}, indent=2)+'\n')
    print(check, records[-1]['result'], stats, flush=True)
assert len(records) == 12 and all(r['result'] == 'PASS' for r in records)
print('KL029_ALL_TWELVE_PACKET_CHECKS_PASS', head, flush=True)
