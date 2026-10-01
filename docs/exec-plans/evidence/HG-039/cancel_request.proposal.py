"""PU feasibility only: independent TEST-local data, no database owner or wire ingress."""
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints

from kineticloop.contracts.commands import CanonicalId, NonNegativeInt, PositiveInt
from kineticloop.identity import ActorRole
from kineticloop.persistence.planning import PlanningIdentity
from kineticloop.persistence.transactions import GuardRequired
from kineticloop.protocol.execution import digest

Key = Annotated[str, StringConstraints(min_length=1, max_length=512, pattern=r"^\S(?:.*\S)?$")]


class TestCancelIntentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    command_kind: Literal["CancelIntent"]
    boundary: Literal["T8"]
    subject_id: CanonicalId
    policy_id: CanonicalId
    environment_id: CanonicalId
    principal: Key
    key: Key
    intent_id: CanonicalId
    attempt_id: CanonicalId
    reservation_id: CanonicalId
    expected_request_revision: PositiveInt
    expected_fence: NonNegativeInt


def bind(request, identity, policy, environment, principal, registration):
    """Trusted owner supplies identity and actual registration; request supplies no authority/hash."""
    if (type(request) is not TestCancelIntentRequest or type(identity) is not PlanningIdentity
            or identity.actor.role is not ActorRole.TEST
            or request.subject_id != str(identity.subject_id)
            or (request.policy_id, request.environment_id, request.principal)
            != (str(policy), str(environment), principal)
            or registration != ("TEST", policy, environment, principal)):
        raise GuardRequired("exact registered TEST cancellation identity required")
    request = TestCancelIntentRequest.model_validate(request.model_dump(mode="python"))
    return identity.key, request.key, digest(request.model_dump(mode="json"))


def locked_basis(request, row):
    """Pure feasibility predicate for fresh SELECT-only S01->S27->S31 observations."""
    if (row["subject_id"] != UUID(request.subject_id)
            or row["intent_id"] != UUID(request.intent_id)
            or row["attempt_id"] != UUID(request.attempt_id)
            or row["reservation_id"] != UUID(request.reservation_id)
            or row["reservation_root"] != row["intent_id"]
            or row["reservation_attempt"] != row["attempt_id"]):
        raise GuardRequired("exact root/attempt/reservation required")
    if row["status"] == "FOUND_VALID_PLAN":
        return "COMPLETED_FACT"
    if (row["status"] not in {"ADMITTED", "RUNNING"}
            or row["request_revision"] != request.expected_request_revision
            or row["fence"] != request.expected_fence
            or row["reservation_status"] not in {"RESERVED", "DISPATCH_INTENT"}):
        raise GuardRequired("terminal/stale cancellation basis")
    return "CANCELLED"


def historical(request, receipt):
    """Bounded successful S02 observation under S01, before current live-root checks."""
    from kineticloop.persistence.transactions import IdempotencyConflict
    if receipt is None:
        return None
    request_hash, status, payload = receipt
    if (request_hash != digest(request.model_dump(mode="json"))
            or status != "SUCCEEDED" or "outcome" not in payload):
        raise IdempotencyConflict("command key request hash/outcome mismatch")
    return {**payload["outcome"], "replayed": True, "executable": False}
