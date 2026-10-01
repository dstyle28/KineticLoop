"""Prepare validator/task tests as drafts only; shared application needs HG035 merge."""
import hashlib
import json
from pathlib import Path

folder = Path('docs/exec-plans/evidence/HG-036')
task = json.loads((folder / 'KL047_definition_draft.json').read_text())
fields = [key for key in task if key not in {'status', 'evidence_refs', 'thread_id', 'id'}]
digests = {key: hashlib.sha256(json.dumps(task[key], ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest() for key in fields}
packet_digest = hashlib.sha256((folder/'KL047_packet_draft.md').read_bytes()).hexdigest()
source = '''# HG036 binds only the unstarted KL047 offline infrastructure definition.
# Future scope/semantic changes require separate governance; historical unrefined
# protected bases retain their original packet and are never relabelled.
FITNESS_EVAL_DEFINITION_DIGESTS = ''' + repr(digests) + '''
FITNESS_EVAL_PACKET_SHA256 = ''' + repr(packet_digest) + '''


def fitness_evaluation_definition_errors(task):
    """Keep source-derived offline scoring separate from quality/release claims."""
    if task.get('id') != 'KL-047':
        return []
    errors = []
    for field, expected in FITNESS_EVAL_DEFINITION_DIGESTS.items():
        actual = hashlib.sha256(json.dumps(
            task.get(field), ensure_ascii=False, sort_keys=True,
            separators=(',', ':'),
        ).encode()).hexdigest()
        if actual != expected:
            errors.append('fitness-eval-definition:KL-047:' + field)
    return errors


def fitness_evaluation_packet_errors(task, text):
    if (task.get('id') != 'KL-047'
            or task.get('packet_refinement') != 'ENFORCEABLE'):
        return []
    digest = hashlib.sha256(text.encode()).hexdigest()
    return ([] if digest == FITNESS_EVAL_PACKET_SHA256
            else ['fitness-eval-packet:KL-047'])


'''
# Emit a legal formatted Python draft, but never apply to tools/harness here.
(folder / 'validator_snippet_draft.py').write_text(source)
