from enum import StrEnum

import pytest

from kineticloop.contracts import ErrorCode


def test_error_registry_wire_values_valid() -> None:
    expected = {
        "SOURCE_IDENTITY_CONFLICT",
        "SUBJECT_MISMATCH",
        "PROVENANCE_MISSING",
        "ASSERTION_SCHEMA_INVALID",
        "BASIS_STALE",
        "ADMISSION_CONFLICT",
        "EVENT_ASSOCIATION_AMBIGUOUS",
        "COMMAND_NOT_AUTHORIZED",
        "CLEARANCE_INSUFFICIENT",
        "APPROVAL_STALE",
        "APPROVAL_CONTENT_MISMATCH",
        "POLICY_DISABLED",
        "DEPENDENCY_UNAVAILABLE",
        "BASIS_INCOMPATIBLE",
        "BUILD_STALE",
        "EPOCH_MISMATCH",
        "POLICY_MISMATCH",
        "QUOTA_EXHAUSTED",
        "INTENT_TERMINAL",
        "REQUEST_CONFLICT",
        "LEASE_LOST",
        "DEADLINE_EXCEEDED",
        "BUDGET_EXHAUSTED",
        "FENCE_MISMATCH",
        "DISPATCH_ALREADY_POSSIBLE",
        "SNAPSHOT_STALE",
        "DEPENDENCY_HASH_MISMATCH",
        "EVIDENCE_INSUFFICIENT",
        "COVERAGE_INCOMPLETE",
        "POLICY_UNCONFIGURED",
        "REQUEST_STALE",
        "HOLD_ACTIVE",
        "AUTH_SCOPE_DENIED",
        "AUTH_EXPIRED",
        "AUTH_REVOKED",
        "CONTENT_MISMATCH",
        "EXECUTION_CONFLICT",
        "SETTLEMENT_CONFLICT",
        "STALE_REAPER_CANDIDATE",
        "KNOWLEDGE_BOUNDARY_VIOLATION",
        "ARTIFACT_UNAVAILABLE",
        "IDEMPOTENCY_KEY_REUSE_WITH_DIFFERENT_PAYLOAD",
        "INVALID_TRANSITION",
        "CONFIG_UNAVAILABLE",
        "BUILD_CLOSED",
        "IDEMPOTENCY_CONFLICT",
        "MEMBERS_NOT_SUPPORTED",
        "BUILD_CHANGED",
        "FACTSET_NOT_READY",
        "IMMUTABLE_ARTIFACT",
        "ARTIFACT_UNKNOWN",
        "VALIDITY_UNDEFINED",
        "ARTIFACT_REVOKED",
        "ARTIFACT_EXPIRED",
        "REGISTRY_UNAVAILABLE",
        "DEPENDENCY_EXPIRED",
    }

    assert issubclass(ErrorCode, StrEnum)
    assert {member.name for member in ErrorCode} == expected
    assert {member.value for member in ErrorCode} == expected
    assert len(ErrorCode) == len(expected)
    with pytest.raises(TypeError):

        class ExtendedErrorCode(ErrorCode):  # type: ignore[misc]
            EXTRA = "EXTRA"
