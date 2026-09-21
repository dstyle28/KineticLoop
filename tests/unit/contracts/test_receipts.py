from dataclasses import FrozenInstanceError
from typing import Callable

import pytest

from kineticloop.contracts import (
    CommandBinding,
    CommandReceipt,
    ErrorCode,
    ReceiptIdentity,
    ReceiptMismatch,
    ReceiptReplay,
    ReceiptResult,
    ResultEntityRef,
    decide_receipt_replay,
    hash_receipt_request,
)

SUBJECT_ID = "6ba7b810-9dad-41d1-80b4-00c04fd430c8"
ENTITY_ID = "6ba7b811-9dad-41d1-80b4-00c04fd430c8"
ACCEPTED_AT = "2026-09-21T16:00:00.000000Z"
COMPLETED_AT = "2026-09-21T16:00:01.000000Z"


def _identity(command_kind: str = "ReceiveEvidence") -> ReceiptIdentity:
    return ReceiptIdentity(
        subject_id=SUBJECT_ID,
        explicit_scope=None,
        actor_scope="subject:self",
        command_kind=command_kind,
        client_key="client-operation-1",
    )


def _result() -> ReceiptResult:
    return ReceiptResult(
        status="opaque-frozen-field-value",
        result_entity_refs=(
            ResultEntityRef(entity_kind="evidence_revision", entity_id=ENTITY_ID),
        ),
        error_code=None,
        accepted_at=ACCEPTED_AT,
        completed_at=COMPLETED_AT,
    )


def _receipt(command_kind: str = "ReceiveEvidence") -> CommandReceipt:
    return CommandReceipt(
        identity=_identity(command_kind),
        request_hash=hash_receipt_request({"operation": command_kind, "revision": 1}),
        result=_result(),
    )


def test_receipt_identity_contract_valid() -> None:
    subject_identity = _identity()
    global_identity = ReceiptIdentity(
        subject_id=None,
        explicit_scope="global:safety-registry",
        actor_scope="management:artifact-revoker",
        command_kind="RevokeArtifact",
        client_key="management-command-1",
    )
    receipt = _receipt()

    assert subject_identity.subject_id == SUBJECT_ID
    assert subject_identity.explicit_scope is None
    assert global_identity.subject_id is None
    assert global_identity.explicit_scope == "global:safety-registry"
    assert type(receipt.request_hash) is str
    assert len(receipt.request_hash) == 64
    assert type(receipt.result.accepted_at) is str
    assert type(receipt.result.result_entity_refs) is tuple
    with pytest.raises(FrozenInstanceError):
        receipt.request_hash = "0" * 64  # type: ignore[misc]


def test_same_key_same_hash_replays_original_result() -> None:
    stored = _receipt()

    decision = decide_receipt_replay(
        stored=stored,
        incoming_identity=stored.identity,
        incoming_request_hash=stored.request_hash,
        command_binding=CommandBinding.for_command(stored.identity.command_kind),
    )

    assert type(decision) is ReceiptReplay
    assert decision.replayed is True
    assert decision.result is stored.result
    assert not hasattr(decision, "authorized")
    assert not hasattr(decision, "execution_permission")
    assert not hasattr(decision, "provider_send_permission")
    with pytest.raises(TypeError):
        ReceiptReplay(result=stored.result, replayed=False)  # type: ignore[call-arg]


@pytest.mark.parametrize(
    ("command_kind", "expected"),
    [
        ("ReceiveEvidence", ErrorCode.IDEMPOTENCY_KEY_REUSE_WITH_DIFFERENT_PAYLOAD),
        ("BeginBuild", ErrorCode.IDEMPOTENCY_CONFLICT),
        ("WriteCandidate", ErrorCode.IDEMPOTENCY_CONFLICT),
        ("RevokeArtifact", ErrorCode.IDEMPOTENCY_CONFLICT),
    ],
)
def test_same_key_different_hash_rejected(
    command_kind: str, expected: ErrorCode
) -> None:
    stored = _receipt(command_kind)
    original_result = stored.result

    decision = decide_receipt_replay(
        stored=stored,
        incoming_identity=stored.identity,
        incoming_request_hash=hash_receipt_request({"operation": command_kind, "revision": 2}),
        command_binding=CommandBinding.for_command(command_kind),
    )

    assert type(decision) is ReceiptMismatch
    assert decision.error_code is expected
    assert stored.result is original_result
    assert ErrorCode.IDEMPOTENCY_CONFLICT.value != (
        ErrorCode.IDEMPOTENCY_KEY_REUSE_WITH_DIFFERENT_PAYLOAD.value
    )


class _StringSubclass(str):
    pass


class _TupleSubclass(tuple[ResultEntityRef, ...]):
    pass


class _ResultRefSubclass(ResultEntityRef):
    pass


@pytest.mark.parametrize(
    "factory",
    [
        lambda: ReceiptIdentity(None, None, "actor", "ReceiveEvidence", "key"),
        lambda: ReceiptIdentity(SUBJECT_ID, "global", "actor", "ReceiveEvidence", "key"),
        lambda: ReceiptIdentity(_StringSubclass(SUBJECT_ID), None, "actor", "cmd", "key"),
        lambda: ReceiptIdentity(SUBJECT_ID.upper(), None, "actor", "cmd", "key"),
        lambda: ReceiptIdentity(SUBJECT_ID, None, _StringSubclass("actor"), "cmd", "key"),
        lambda: ReceiptResult(
            "status", [], None, ACCEPTED_AT, None  # type: ignore[arg-type]
        ),
        lambda: ReceiptResult("status", _TupleSubclass(), None, ACCEPTED_AT, None),
        lambda: ReceiptResult(
            "status",
            (_ResultRefSubclass("entity", ENTITY_ID),),
            None,
            ACCEPTED_AT,
            None,
        ),
        lambda: ReceiptResult(
            "status", (), "AUTH_EXPIRED", ACCEPTED_AT, None  # type: ignore[arg-type]
        ),
        lambda: ReceiptResult("status", (), None, "2026-09-21T16:00:00Z", None),
        lambda: ReceiptResult("status", (), None, ACCEPTED_AT, "not-a-time"),
        lambda: CommandReceipt(_identity(), "A" * 64, _result()),
        lambda: CommandReceipt(_identity(), _StringSubclass("a" * 64), _result()),
        lambda: ReceiptMismatch("IDEMPOTENCY_CONFLICT"),  # type: ignore[arg-type]
        lambda: ReceiptIdentity(  # extra model-supplied authority is not a field
            subject_id=SUBJECT_ID,
            explicit_scope=None,
            actor_scope="actor",
            command_kind="cmd",
            client_key="key",
            authorized=True,  # type: ignore[call-arg]
        ),
        lambda: ReceiptIdentity(  # type: ignore[misc]  # duplicate field input
            SUBJECT_ID,
            None,
            "actor",
            "cmd",
            "key",
            client_key="replacement",
        ),
    ],
)
def test_receipt_invalid_input_rejected(factory: Callable[[], object]) -> None:
    with pytest.raises((TypeError, ValueError)):
        factory()


def test_receipt_invalid_input_rejected_without_inventing_lifecycle_correlation() -> None:
    opaque = ReceiptResult(
        status="not-interpreted-by-base-contract",
        result_entity_refs=(),
        error_code=ErrorCode.AUTH_EXPIRED,
        accepted_at=ACCEPTED_AT,
        completed_at=None,
    )

    assert opaque.status == "not-interpreted-by-base-contract"
    assert opaque.error_code is ErrorCode.AUTH_EXPIRED


def test_receipt_invalid_input_rejected_for_binding_or_identity_mismatch() -> None:
    stored = _receipt("BeginBuild")
    other_identity = ReceiptIdentity(
        subject_id=SUBJECT_ID,
        explicit_scope=None,
        actor_scope="subject:self",
        command_kind="BeginBuild",
        client_key="different-key",
    )

    with pytest.raises(ValueError):
        CommandBinding(
            command_kind="BeginBuild",
            mismatch_error=ErrorCode.IDEMPOTENCY_KEY_REUSE_WITH_DIFFERENT_PAYLOAD,
        )
    with pytest.raises(ValueError):
        decide_receipt_replay(
            stored=stored,
            incoming_identity=other_identity,
            incoming_request_hash=stored.request_hash,
            command_binding=CommandBinding.for_command("BeginBuild"),
        )
    with pytest.raises(ValueError):
        decide_receipt_replay(
            stored=stored,
            incoming_identity=stored.identity,
            incoming_request_hash=stored.request_hash,
            command_binding=CommandBinding.for_command("ReceiveEvidence"),
        )
