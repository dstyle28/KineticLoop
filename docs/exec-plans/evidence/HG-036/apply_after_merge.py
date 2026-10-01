"""Ratify HG036 only after recorded actual HG035 normal merge and rebased HEAD."""
import hashlib
import importlib.util
import json
import re
import subprocess
from pathlib import Path

root = Path.cwd()
folder = root / 'docs/exec-plans/evidence/HG-036'
merge = json.loads((folder / 'HG035_merged.json').read_text())
assert merge['state'] == 'MERGED' and merge['mergedAt']
assert merge['headRefName'] == 'codex/hg035-protocol-execution-packet'
sha = merge['mergeCommit']['oid']
parents = subprocess.check_output(['git', 'rev-list', '--parents', '-n', '1', sha], text=True).split()
assert len(parents) == 3, 'HG035 must have an actual normal two-parent merge'
subprocess.run(['git', 'merge-base', '--is-ancestor', sha, 'HEAD'], check=True)
assert (root/'docs/exec-plans/governance/HG-035.yaml').is_file()
assert not list((root/'docs/exec-plans/completed').glob('KL-047_RESULT.*'))
assert not (root/'src/kineticloop/evaluation').exists()
spec = importlib.util.spec_from_file_location('v',root/'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
task = json.loads((folder/'KL047_definition_draft.json').read_text())
backlog = json.loads((root/v.BACKLOG).read_text())
old = next(t for t in backlog['tasks'] if t['id'] == 'KL-047')
assert old['status'] == 'NOT_STARTED'
assert old['depends_on'] == ['KL-005','KL-018']
backlog['tasks'][backlog['tasks'].index(old)] = task
(root/v.BACKLOG).write_text(json.dumps(backlog,indent=2)+'\n')
trace = json.loads((root/v.TRACEABILITY).read_text())
old_trace = next(t for t in trace['tasks'] if t['id'] == 'KL-047')
trace['tasks'][trace['tasks'].index(old_trace)] = v.traceability_projection(task)
(root/v.TRACEABILITY).write_text(json.dumps(trace,indent=2)+'\n')
(root/'docs/exec-plans/active/KL-047.md').write_bytes((folder/'KL047_packet_draft.md').read_bytes())
locks = root/'docs/harness/RESOURCE_LOCKS.md'
content = locks.read_text()
assert '- `fitness_eval_contract`' not in content
content = content.replace('- `transaction_interfaces`','- `transaction_interfaces`\n- `fitness_eval_contract`')
locks.write_text(content)
path = root/'tools/harness/validate_harness.py'
source = path.read_text()
assert 'FITNESS_EVAL_DEFINITION_DIGESTS' not in source
source = source.replace('def task_definition_errors(', (folder/'validator_snippet_draft.py').read_text()+'def task_definition_errors(',1)
source = source.replace('def packet_errors(task, text):\n    errors = []', 'def packet_errors(task, text):\n    errors = fitness_evaluation_packet_errors(task, text)',1)
needle = 'if (name in M2_REFINED_TASK_IDS or ('
assert source.count(needle) == 1
source = source.replace(needle,"if (name in M2_REFINED_TASK_IDS or (name == 'KL-047'\n            and task.get('packet_refinement') == 'ENFORCEABLE') or (",1)
start = source.index('def task_definition_errors(')
left, right = source[:start], source[start:]
needle = "    for task in backlog['tasks']:\n        name = task['id']\n"
assert needle in right
right = right.replace(needle,needle+"        if (name == 'KL-047' and (not revision\n                or task.get('packet_refinement') == 'ENFORCEABLE')):\n            errors.extend(fitness_evaluation_definition_errors(task))\n",1)
pattern = r'sorted\((M2_REFINED_TASK_IDS \| WAVE_REFINED_TASK_IDS[^\n]*?)\)'
right, count = re.subn(pattern,lambda m: "sorted("+m.group(1)+" | {'KL-047'})",right,count=1)
assert count == 1, 'generic collision-set hook requires inspection'
path.write_text(left+right)
(root/'tests/harness/test_fitness_evaluation_scope.py').write_bytes((folder/'governance_test_draft.py').read_bytes())
for meta, groups in [('CURRENT_DOCUMENT_INDEX.json',['documents','machine_readable']), ('HARNESS_DOCUMENT_MANIFEST.json',['files'])]:
    data = json.loads((root/meta).read_text())
    for group in groups:
        for entry in data[group]:
            blob = (root/entry['path']).read_bytes()
            entry['sha256'] = hashlib.sha256(blob).hexdigest()
            if 'bytes' in entry:
                entry['bytes'] = len(blob)
    (root/meta).write_text(json.dumps(data,indent=2)+'\n')
print('Applied exact HG036 proposal after actual HG035 merge ' + sha)
print('All prospective KL047 checks/product/gate/release obligations NOT_RUN; no implementation')
