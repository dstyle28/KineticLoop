"""Immutable base contracts shared by KineticLoop command owners."""

from kineticloop.contracts.errors import ErrorCode
from kineticloop.contracts.receipts import (
    CommandBinding,
    CommandReceipt,
    ReceiptIdentity,
    ReceiptMismatch,
    ReceiptReplay,
    ReceiptResult,
    ResultEntityRef,
    decide_receipt_replay,
    hash_receipt_request,
)
from kineticloop.contracts.shadow import (
    SHADOW_ARTIFACT_WIRE_SCHEMA,
    TEST_ONLY_SCOPE_WIRE_SCHEMA,
    AuthorizationScope,
    ExecutionDisposition,
    IsolationBoundary,
    ShadowContractError,
    ShadowEvaluationArtifact,
    ShadowMode,
    ShadowPersistenceBoundary,
    TestOnlyAuthorizationScope,
)

__all__ = [
    "CommandBinding",
    "CommandReceipt",
    "ErrorCode",
    "ExecutionDisposition",
    "IsolationBoundary",
    "ReceiptIdentity",
    "ReceiptMismatch",
    "ReceiptReplay",
    "ReceiptResult",
    "ResultEntityRef",
    "SHADOW_ARTIFACT_WIRE_SCHEMA",
    "ShadowContractError",
    "ShadowEvaluationArtifact",
    "ShadowMode",
    "ShadowPersistenceBoundary",
    "TEST_ONLY_SCOPE_WIRE_SCHEMA",
    "TestOnlyAuthorizationScope",
    "AuthorizationScope",
    "decide_receipt_replay",
    "hash_receipt_request",
]
