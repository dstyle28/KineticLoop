"""Print proposed validator hooks; deliberately makes no shared writes."""
from pathlib import Path

source = Path('tools/harness/validate_harness.py').read_text()
assert 'def task_definition_errors(' in source
assert 'def packet_errors(task, text):\n    errors = []' in source
print('After actual HG035 normal merge, insert validator_snippet_draft.py before task_definition_errors.')
print('Hook fitness_evaluation_packet_errors into packet_errors and full projected fields for enforceable KL047.')
print('Hook fitness_evaluation_definition_errors when current or historical enforceable.')
print('Include enforceable KL047 in the generic resource collision set while preserving all existing identities.')
print('Register exactly fitness_eval_contract in RESOURCE_LOCKS; refresh only changed indexed hashes/bytes.')
print('NOT_RUN all future implementation checks. No shared write, review or PR before HG035 merge.')
