"""KL-014 typed result serialization and safety tests."""

import json
from typing import Any, Literal, get_args, get_origin

import pytest
from pydantic import ValidationError

from kineticloop.contracts import (
    PUBLIC_COMMAND_BY_KIND,
    PUBLIC_SUCCESS_RESULT_BY_KIND,
    PUBLIC_SUCCESS_RESULT_MODELS,
    CommandRejected,
    ErrorCode,
    PermitDispatchSuccess,
    parse_result,
)

ID = "6ba7b810-9dad-41d1-80b4-00c04fd430c8"
HASH = "a" * 64


def result_payload(model: Any) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "kineticloop-command-result-v1",
        "result_kind": "success",
        "receipt_id": ID,
        "result_id": ID,
        "entity_id": ID,
        "outcome_hash": HASH,
        "completed_at": "2026-09-24T16:00:00.000000Z",
        "replayed": False,
    }
    for name, field in model.model_fields.items():
        if name in payload:
            continue
        if get_origin(field.annotation) is Literal:
            payload[name] = get_args(field.annotation)[0]
        elif field.annotation is bool:
            payload[name] = True
        else:
            raise AssertionError(f"unhandled result field {name}")
    return payload


def test_command_result_roundtrip() -> None:
    assert set(PUBLIC_SUCCESS_RESULT_BY_KIND) == set(PUBLIC_COMMAND_BY_KIND)
    assert len(PUBLIC_SUCCESS_RESULT_MODELS) == 39
    assert len(set(PUBLIC_SUCCESS_RESULT_MODELS)) == 39

    for kind, model in PUBLIC_SUCCESS_RESULT_BY_KIND.items():
        result = model.model_validate(result_payload(model))
        assert result.command_kind == kind
        assert type(parse_result(result.to_canonical_json())) is model
        assert type(parse_result(json.loads(result.to_canonical_json()))) is model
        with pytest.raises(ValidationError):
            model.model_validate(result.model_dump(mode="python") | {"extra": True})

    rejected = CommandRejected(
        schema_version="kineticloop-command-result-v1",
        result_kind="rejected",
        command_kind="CommitBundle",
        receipt_id=ID,
        error_code=ErrorCode.HOLD_ACTIVE,
        rejected_at="2026-09-24T16:00:00.000000Z",
        replayed=False,
    )
    assert parse_result(rejected.to_canonical_json()) == rejected
    assert parse_result(json.loads(rejected.to_canonical_json())) == rejected

    with pytest.raises(ValidationError):
        CommandRejected(
            schema_version="kineticloop-command-result-v1",
            result_kind="rejected",
            command_kind="IssueAuthorization",
            receipt_id=ID,
            error_code=ErrorCode.HOLD_ACTIVE,
            rejected_at="2026-09-24T16:00:00.000000Z",
            replayed=False,
        )


def test_dispatch_replay_never_grants_second_provider_send() -> None:
    payload = result_payload(PermitDispatchSuccess)
    payload["replayed"] = True
    payload["provider_send_allowed"] = True
    with pytest.raises(ValidationError, match="another provider send"):
        PermitDispatchSuccess.model_validate(payload)

    payload["provider_send_allowed"] = False
    assert PermitDispatchSuccess.model_validate(payload).provider_send_allowed is False
