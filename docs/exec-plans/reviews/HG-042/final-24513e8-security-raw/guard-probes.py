"""PU guard-depth probes for the refined packet; never connect to PostgreSQL."""
import json
from uuid import uuid4

from pydantic import ValidationError
from kineticloop.contracts.commands import StartSession, ProductionScope, parse_command
from kineticloop.contracts.shadow import ShadowEvaluationArtifact
from kineticloop.identity import ActorRole, RoleIdentity
from kineticloop.protocol.execution import ExecutionIdentity, command_digest
from kineticloop.persistence.protocol_execution import ProtocolExecutionService
from kineticloop.persistence.transactions import GuardRequired
from kineticloop.persistence.subject_scope import SubjectScopeDenial

subject, policy, environment = uuid4(), uuid4(), uuid4()
identity = ExecutionIdentity(RoleIdentity(str(uuid4()), ActorRole.TEST), subject, policy, environment, 'kl_test_subject_1_login')
wire = {
    'schema_version': 'kineticloop-command-v1', 'command_kind': 'StartSession', 'boundary': 'T7',
    'command_id': str(uuid4()), 'actor': {'schema': 'kineticloop-role-identity-v1', 'identity_id': str(subject), 'role': 'subject'},
    'idempotency_key': 'security-production-scope', 'request_hash': 'a' * 64,
    'subject_id': str(subject), 'explicit_scope': None, 'authorization_scope': {'scope': 'production', 'subject_id': str(subject)},
    'session_id': str(uuid4()), 'prescription_id': str(uuid4()), 'authorization_id': str(uuid4()),
    'action_key': 'start', 'binding_revision': 1, 'expected_authorization_epoch': 0,
    'content_hash': 'a' * 64, 'artifact_dependency_closure_hash': 'b' * 64,
}
command = parse_command(wire)
wire['request_hash'] = command_digest(command)
command = parse_command(wire)
assert type(command) is StartSession and type(command.authorization_scope) is ProductionScope
assert command_digest(command) == command.request_hash
try:
    identity.require_wire(command)
except ValueError as error:
    assert str(error) == 'authenticated TEST command binding mismatch'
else:
    raise AssertionError('production scope was accepted')
shadow_wire = json.loads(json.dumps(wire))
shadow_wire['authorization_scope']['scope'] = 'shadow'
try:
    parse_command(shadow_wire)
except ValidationError as error:
    assert any(e['type'] == 'union_tag_invalid' for e in error.errors())
else:
    raise AssertionError('shadow scope was parsed')

class NoDatabase:
    def __getattr__(self, name):
        raise AssertionError('Database access before strict owner ingress: ' + name)
service = ProtocolExecutionService(NoDatabase(), identity)
artifact = ShadowEvaluationArtifact(str(uuid4()), str(uuid4()))
assert ShadowEvaluationArtifact.from_json(artifact.to_json()) == artifact
denials = []
for method, expected in (('commit_full', 'closed full commit request required'), ('commit', 'strict CommitBundle required'), ('start', 'strict StartSession required'), ('continue_session', 'strict ContinueSession required'), ('resume', 'strict ResumeSession required')):
    for value in (artifact, artifact.to_payload()):
        try:
            getattr(service, method)(value)
        except GuardRequired as error:
            assert str(error) == expected
            denials.append({'method': method, 'input': type(value).__name__, 'guard': str(error), 'db_access': False})
        else:
            raise AssertionError(method)
denial = SubjectScopeDenial()
assert denial.code == 'SUBJECT_SCOPE_DENIED'
assert dict(denial.payload) == {'error': 'subject_scope_denied'}
assert denial.timing_class == 'BOUNDED_SCOPE_LOOKUP'
print(json.dumps({'layer': 'PU', 'valid_production_command_rejected_by_real_require_wire': True, 'shadow_scope_rejected_by_real_parser': True, 'strict_owner_ingress_denials': denials, 'timing_class_is_metadata_only': True, 'db_or_transaction_guard_claim': False}, indent=2))
