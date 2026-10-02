"""Focused feasibility probes of the actual merged pure owners, not product PASS."""
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from kineticloop.contracts.artifacts import ArtifactDependencyError, validate_complete_dependency_closure
from kineticloop.contracts.commands import StartSession
from kineticloop.identity import ActorRole, RoleIdentity
from kineticloop.protocol.authorization import AuthorizationEvaluationError, ValidityDependency, evaluate_validity_closure
from kineticloop.protocol.execution import ExecutionIdentity, command_digest

a, b, c = [str(uuid4()) for _ in range(3)]
# Explicit complete transitive registration can contain the additional A->C edge.
graph = {a: (b, c), b: (c,), c: ()}
assert validate_complete_dependency_closure((a, b, c), graph) == tuple(sorted((a, b, c)))
for incomplete in ((a,), (a, b)):
    try:
        validate_complete_dependency_closure(incomplete, graph)
    except ArtifactDependencyError as error:
        assert 'incomplete' in str(error)
    else:
        raise AssertionError('actual complete-closure validator accepted omitted leaf')
now = datetime(2026, 10, 2, tzinfo=UTC)
deps = tuple(ValidityDependency('ARTIFACT', node, 1, now, now + timedelta(minutes=10),
                               artifact_kind='ENGINE', dependency_ids=graph[node]) for node in (a, b, c))
valid = evaluate_validity_closure(authoritative_now=now, dependencies=deps)
assert valid.valid_until == now + timedelta(minutes=10)
assert {entry['identity'] for entry in valid.dependencies} == {a, b, c}
try:
    evaluate_validity_closure(authoritative_now=now, dependencies=(*deps[:2], replace(deps[2], revoked=True)))
except AuthorizationEvaluationError as error:
    assert str(error) == 'dependency current admission is unprovable'
else:
    raise AssertionError('actual evaluator accepted revoked leaf')
# Construct a genuine closed production command, then reach require_wire separately.
subject, policy, environment = uuid4(), uuid4(), uuid4()
actor = RoleIdentity(str(subject), ActorRole.SUBJECT)
payload = {
    'schema_version': 'kineticloop-command-v1', 'command_kind': 'StartSession', 'boundary': 'T7',
    'command_id': str(uuid4()), 'actor': actor.to_payload(), 'subject_id': str(subject),
    'idempotency_key': 'hg042-production-probe', 'request_hash': 'a' * 64, 'explicit_scope': None,
    'authorization_scope': {'scope': 'production', 'subject_id': str(subject)},
    'session_id': str(uuid4()), 'prescription_id': str(uuid4()), 'authorization_id': str(uuid4()),
    'action_key': 'start', 'binding_revision': 1, 'expected_authorization_epoch': 0,
    'content_hash': 'b' * 64, 'artifact_dependency_closure_hash': 'c' * 64,
}
production = StartSession.model_validate_json(json.dumps(payload))
payload['request_hash'] = command_digest(production)
production = StartSession.model_validate_json(json.dumps(payload))
identity = ExecutionIdentity(RoleIdentity(str(uuid4()), ActorRole.TEST), UUID(str(subject)), policy,
                             environment, 'kl_test_subject_1_login')
try:
    identity.require_wire(production)
except ValueError as error:
    assert str(error) == 'authenticated TEST command binding mismatch'
else:
    raise AssertionError('TEST require_wire accepted genuine production command')
payload['authorization_scope']['scope'] = 'shadow'
try:
    StartSession.model_validate_json(json.dumps(payload))
except ValueError:
    pass
else:
    raise AssertionError('public command parser accepted shadow scope')
print(json.dumps({'b17_actual_complete_closure_positive': True, 'b17_omitted_leaf_denied': True,
                  'b17_actual_revoked_leaf_denied': True, 'tied_minimum_preserved': True,
                  'valid_production_command_parsed_then_require_wire_denied': True,
                  'shadow_scope_denied_by_public_parser': True, 'product_requirement_pass_claims': []}, indent=2))
