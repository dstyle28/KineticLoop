"""HG039 bounded packet correspondence and independent TEST-request feasibility."""
from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError

from kineticloop.contracts.commands import (
    PUBLIC_COMMAND_MODELS,
    CancelIntent,
    SubjectCommand,
    parse_command,
)
from kineticloop.identity import ActorRole, RoleIdentity
from kineticloop.persistence.planning import PlanningIdentity
from kineticloop.persistence.transactions import GuardRequired, IdempotencyConflict

ROOT = Path(__file__).resolve().parents[2]
PROPOSAL = ROOT / 'docs/exec-plans/evidence/HG-039/cancel_request.proposal.py'
spec = importlib.util.spec_from_file_location('hg039_proposal', PROPOSAL)
assert spec is not None and spec.loader is not None
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)


def uid(n: int) -> UUID:
    return UUID(f'00000000-0000-8000-8000-{n:012x}')


def payload() -> dict[str, Any]:
    return {'command_kind': 'CancelIntent', 'boundary': 'T8', 'subject_id': str(uid(1)),
            'policy_id': str(uid(2)), 'environment_id': str(uid(3)),
            'principal': 'kl_test_subject_1_login', 'key': 'cancel-root',
            'intent_id': str(uid(4)), 'attempt_id': str(uid(5)), 'reservation_id': str(uid(6)),
            'expected_request_revision': 1, 'expected_fence': 1}


def identity(role: ActorRole = ActorRole.TEST) -> PlanningIdentity:
    return PlanningIdentity(RoleIdentity(str(uid(7)), role), uid(1))


def bind(request: Any, actor: PlanningIdentity | None = None, **changes: Any) -> Any:
    args = {'identity': identity() if actor is None else actor, 'policy': uid(2),
            'environment': uid(3), 'principal': 'kl_test_subject_1_login',
            'registration': ('TEST', uid(2), uid(3), 'kl_test_subject_1_login')}
    args.update(changes)
    return candidate.bind(request, **args)


def basis() -> dict[str, Any]:
    return {'subject_id': uid(1), 'intent_id': uid(4), 'attempt_id': uid(5),
            'reservation_id': uid(6), 'reservation_root': uid(4), 'reservation_attempt': uid(5),
            'status': 'RUNNING', 'request_revision': 1, 'fence': 1,
            'reservation_status': 'RESERVED'}


def test_independent_positive_request_is_feasible_and_immutable() -> None:
    cls = candidate.TestCancelIntentRequest
    assert not issubclass(cls, SubjectCommand)
    assert cls not in PUBLIC_COMMAND_MODELS
    request = cls.model_validate(payload())
    actor, key, digest = bind(request)
    assert actor == identity().key and key == 'cancel-root' and len(digest) == 64
    assert bind(cls.model_validate(dict(reversed(list(payload().items())))))[2] == digest
    assert bind(cls.model_validate({**payload(), 'expected_fence': 2}))[2] != digest
    with pytest.raises(ValidationError):
        request.expected_fence = 2
    assert candidate.locked_basis(request, basis()) == 'CANCELLED'
    assert candidate.locked_basis(request, {**basis(), 'reservation_status': 'DISPATCH_INTENT'}) == 'CANCELLED'
    assert candidate.locked_basis(request, {**basis(), 'status': 'FOUND_VALID_PLAN'}) == 'COMPLETED_FACT'


@pytest.mark.parametrize('field,value', [
    ('subject_id', 'invalid'), ('policy_id', 2), ('environment_id', None),
    ('key', ''), ('key', ' '), ('key', ' cancel'), ('key', 'x' * 513),
    ('principal', ''), ('intent_id', uid(4)), ('attempt_id', 'foreign'),
    ('reservation_id', False), ('expected_request_revision', True),
    ('expected_request_revision', 0), ('expected_request_revision', '1'),
    ('expected_fence', False), ('expected_fence', -1), ('expected_fence', '1'),
    ('boundary', 'T4'), ('command_kind', 'CommitBundle'),
    ('actor', {'role': 'test'}), ('request_hash', '0' * 64), ('authorization_scope', 'production'),
])
def test_strict_types_bounds_and_self_attested_authority_reject(field: str, value: Any) -> None:
    with pytest.raises(ValidationError):
        candidate.TestCancelIntentRequest.model_validate({**payload(), field: value})


@pytest.mark.parametrize('field', ['subject_id', 'policy_id', 'environment_id', 'principal'])
def test_foreign_request_scope_rejects(field: str) -> None:
    value = 'kl_test_subject_2_login' if field == 'principal' else str(uid(99))
    request = candidate.TestCancelIntentRequest.model_validate({**payload(), field: value})
    with pytest.raises(GuardRequired):
        bind(request)


@pytest.mark.parametrize('changes', [
    {'registration': None}, {'registration': ('PRODUCTION', uid(2), uid(3), 'kl_test_subject_1_login')},
    {'registration': ('TEST', uid(99), uid(3), 'kl_test_subject_1_login')},
    {'registration': ('TEST', uid(2), uid(99), 'kl_test_subject_1_login')},
    {'registration': ('TEST', uid(2), uid(3), 'kl_test_subject_2_login')},
    {'identity': identity(ActorRole.SUBJECT)}, {'identity': object()},
    {'identity': PlanningIdentity(RoleIdentity(str(uid(7)), ActorRole.TEST), uid(99))},
])
def test_untrusted_identity_and_registration_reject(changes: dict[str, Any]) -> None:
    with pytest.raises(GuardRequired):
        bind(candidate.TestCancelIntentRequest.model_validate(payload()), **changes)


@pytest.mark.parametrize('field,value', [
    ('subject_id', uid(99)), ('intent_id', uid(99)), ('attempt_id', uid(99)),
    ('reservation_id', uid(99)), ('reservation_root', uid(99)), ('reservation_attempt', uid(99)),
    ('status', 'CANCELLED'), ('status', 'DEADLINE_EXCEEDED'),
    ('request_revision', 2), ('fence', 2), ('reservation_status', 'UNKNOWN'),
])
def test_locked_root_request_fence_and_reservation_denials(field: str, value: Any) -> None:
    with pytest.raises(GuardRequired):
        candidate.locked_basis(candidate.TestCancelIntentRequest.model_validate(payload()),
                               {**basis(), field: value})


@pytest.mark.parametrize('boundary', ['T4', 'T8'])
def test_original_public_test_only_cancel_still_rejects(boundary: str) -> None:
    body = {'schema_version': 'kineticloop-command-v1', 'command_kind': 'CancelIntent',
            'boundary': boundary, 'command_id': str(uid(8)),
            'actor': {'schema': 'kineticloop-role-identity-v1', 'identity_id': str(uid(7)), 'role': 'test'},
            'idempotency_key': 'cancel-root', 'request_hash': '0' * 64,
            'subject_id': str(uid(1)), 'explicit_scope': None,
            'authorization_scope': {'scope': 'test_only', 'subject_id': str(uid(1)),
                                    'policy_id': str(uid(2)), 'environment_id': str(uid(3)),
                                    'subject_boundary': 'isolated_non_production',
                                    'policy_boundary': 'isolated_non_production',
                                    'environment_boundary': 'isolated_non_production',
                                    'direct_write_allowed': False, 'command_owner_guard_required': True},
            'intent_id': str(uid(4)), 'expected_request_revision': 1, 'expected_fence': 1}
    with pytest.raises(ValidationError, match='TEST_ONLY is admitted only at T6/T7'):
        parse_command(json.dumps(body))
    assert len(PUBLIC_COMMAND_MODELS) == 39
    assert CancelIntent in PUBLIC_COMMAND_MODELS


def test_packet_check_scope_and_projections_preserve_dc_oracles() -> None:
    spec = importlib.util.spec_from_file_location('hg039_validator', ROOT / 'tools/harness/validate_harness.py')
    assert spec is not None and spec.loader is not None
    v = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(v)
    backlog = json.loads((ROOT / v.BACKLOG).read_text())
    task = next(t for t in backlog['tasks'] if t['id'] == 'KL-026')
    packet = (ROOT / 'docs/exec-plans/active/KL-026.md').read_text()
    assert v.m3_next_wave_definition_errors(task) == []
    assert v.packet_errors(task, packet) == []
    trace = json.loads((ROOT / v.TRACEABILITY).read_text())['tasks']
    assert next(t for t in trace if t['id'] == 'KL-026') == v.traceability_projection(task)
    old = json.loads(subprocess.check_output(['git', 'show',
        '74cd5b3:KineticLoop_Harness_Backlog_v0.2.json'], cwd=ROOT))
    prior = next(t for t in old['tasks'] if t['id'] == 'KL-026')
    allowed = {'check_contracts', 'checks_required_for_this_task', 'context_files'}
    assert {k for k in task if task[k] != prior[k]} == allowed
    assert [c for c in task['check_contracts'] if c['check_id'] != 'cancellation_identity_pu'] == prior['check_contracts']
    assert task['write_paths'] == prior['write_paths']
    assert task['status'] == 'NOT_STARTED' and task['evidence_refs'] == []
    check = next(c for c in task['check_contracts'] if c['check_id'] == 'cancellation_identity_pu')
    assert check['command'].endswith('tests/unit/protocol/test_interleaving_namespace.py::test_cancellation_identity')
    for phrase in ('repeat exact persisted registration under S01', 'server-side', 'no caller actor',
                   'concurrent same-key historical replay', 'terminal-success preservation',
                   'No SUBJECT translation', 'public registry/validator remain unchanged'):
        assert phrase in packet
        assert v.packet_errors(task, packet.replace(phrase, 'bypass', 1))
    altered = copy.deepcopy(task)
    altered['write_paths'].append('src/kineticloop/contracts/commands.py')
    assert v.m3_next_wave_definition_errors(altered)


@pytest.mark.parametrize('path', ['tests/db/test_protocol_interleavings.py',
                                 'tests/unit/protocol/test_interleaving_namespace.py'])
def test_legitimate_candidate_can_install_in_existing_test_scope(tmp_path: Path, path: str) -> None:
    installed = tmp_path / path
    assert not installed.exists()  # Absence is feasible; no lifecycle import or missing-check PASS.
    installed.parent.mkdir(parents=True)
    installed.write_text(PROPOSAL.read_text())
    spec = importlib.util.spec_from_file_location('hg039_installed_' + installed.stem, installed)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    request = module.TestCancelIntentRequest.model_validate(payload())
    assert not issubclass(type(request), SubjectCommand)
    assert module.bind(request, identity(), uid(2), uid(3), 'kl_test_subject_1_login',
                       ('TEST', uid(2), uid(3), 'kl_test_subject_1_login'))[0] == identity().key
    assert module.locked_basis(request, basis()) == 'CANCELLED'
    assert 'execute_command(' not in PROPOSAL.read_text()
    assert 'model_construct' not in PROPOSAL.read_text()


def test_forged_copy_and_wrong_type_reject() -> None:
    request = candidate.TestCancelIntentRequest.model_validate(payload())
    with pytest.raises(GuardRequired):
        bind(object())
    with pytest.raises(ValidationError):
        bind(request.model_copy(update={"expected_fence": True}))


def test_server_computed_hash_conflict_and_non_executable_historical_fact() -> None:
    request = candidate.TestCancelIntentRequest.model_validate(payload())
    receipt = (bind(request)[2], "SUCCEEDED", {"outcome": {"intent_id": str(uid(4)), "status": "CANCELLED"}})
    original = copy.deepcopy(receipt)
    assert candidate.historical(request, None) is None
    replay = candidate.historical(request, receipt)
    assert replay == {**receipt[2]["outcome"], "replayed": True, "executable": False}
    assert receipt == original
    different = candidate.TestCancelIntentRequest.model_validate({**payload(), "expected_fence": 2})
    with pytest.raises(IdempotencyConflict):
        candidate.historical(different, receipt)
    with pytest.raises(IdempotencyConflict):
        candidate.historical(request, ("0" * 64, "SUCCEEDED", receipt[2]))
    with pytest.raises(IdempotencyConflict):
        candidate.historical(request, (receipt[0], "FAILED", receipt[2]))
