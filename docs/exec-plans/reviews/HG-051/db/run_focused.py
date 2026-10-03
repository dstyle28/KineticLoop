from pathlib import Path
import subprocess
import time

root = Path(__file__).resolve().parents[5]
temp = Path('/private/tmp/hg051-db-review-7141')
report = Path(__file__).resolve().parent
command = [str(root / '.venv/bin/python'), '-m', 'pytest', '-q',
           'tests/harness/test_compact_evidence.py',
           'tests/harness/test_source_decision_scope.py',
           'tests/harness/test_review_evidence_provenance.py',
           'tests/harness/test_m3_milestone_closure.py',
           'tests/harness/test_validator.py',
           '-k', 'archiv or hg051 or source_decision_scope or manifest_tamper or bounded_single_member or decoded_reserved or exact_retrieval',
           '-n', '2', '--junitxml=' + str(report / 'focused.xml'),
           '--basetemp=' + str(temp / 'focused-temp')]
start = time.monotonic()
with (report / 'focused.log').open('w') as log:
    result = subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT)
(report / 'focused-exit.txt').write_text(
    'Reviewed implementation: 7141b1dfe48df8f0e25429cf9ff646af6de4b5ce\n'
    'Committed task tested revision: 5debfe1b41a26c0b3f985917b80995a9eb38b92e\n'
    + 'Reviewer command: ' + repr(command) + '\n'
    + 'Exit code: ' + str(result.returncode) + '\n'
    + 'Elapsed seconds: ' + str(time.monotonic() - start) + '\n')
raise SystemExit(result.returncode)
