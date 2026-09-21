"""Immutable S02 command-receipt base contracts.

These values carry receipt identity and historical result data only. They do
not admit evidence, authorize execution, grant a provider send, implement a
receipt lifecycle, or replace the later CommandGateway transaction boundary.
"""

import hmac
import re
from dataclasses import dataclass, field

from kineticloop.contracts.errors import ErrorCode
from kineticloop.primitives import canonical_id, canonical_sha256, canonical_utc

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
_SECTION_11_CONFLICT_COMMANDS = frozenset(
    {"BeginBuild", "WriteCandidate", "RevokeArtifact"}
)


def _strict_nonempty_string(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a built-in string")
    if not value:
        raise ValueError(f"{field_name} must not be empty")
    return value


def _strict_hash(value: object) -> str:
    if type(value) is not str:
        raise TypeError("request_hash must be a built-in string")
    if _SHA256_HEX.fullmatch(value) is None:
        raise ValueError("request_hash must be 64 lower-case hexadecimal characters")
    return value


def _strict_utc(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a built-in RFC 3339 string")
    if canonical_utc(value) != value:
        raise ValueError(f"{field_name} must already use canonical UTC wire form")
    return value


@dataclass(frozen=True, slots=True)
class ReceiptIdentity:
    """The frozen S02 uniqueness identity.

    Exactly one of ``subject_id`` and ``explicit_scope`` is required. Global
    management commands therefore use their real explicit namespace instead
    of manufacturing a subject identifier.
    """

    subject_id: str | None
    explicit_scope: str | None
    actor_scope: str
    command_kind: str
    client_key: str

    def __post_init__(self) -> None:
        if (self.subject_id is None) == (self.explicit_scope is None):
            raise ValueError("exactly one of subject_id and explicit_scope is required")
        if self.subject_id is not None:
            if type(self.subject_id) is not str:
                raise TypeError("subject_id must be a built-in string")
            canonical_id(self.subject_id)
        if self.explicit_scope is not None:
            _strict_nonempty_string(self.explicit_scope, "explicit_scope")
        _strict_nonempty_string(self.actor_scope, "actor_scope")
        _strict_nonempty_string(self.command_kind, "command_kind")
        _strict_nonempty_string(self.client_key, "client_key")


@dataclass(frozen=True, slots=True)
class ResultEntityRef:
    """A typed reference to an entity created or selected by a command."""

    entity_kind: str
    entity_id: str

    def __post_init__(self) -> None:
        _strict_nonempty_string(self.entity_kind, "entity_kind")
        if type(self.entity_id) is not str:
            raise TypeError("entity_id must be a built-in string")
        canonical_id(self.entity_id)


@dataclass(frozen=True, slots=True)
class ReceiptResult:
    """Opaque historical S02 result fields without invented lifecycle rules."""

    status: str
    result_entity_refs: tuple[ResultEntityRef, ...]
    error_code: ErrorCode | None
    accepted_at: str
    completed_at: str | None

    def __post_init__(self) -> None:
        _strict_nonempty_string(self.status, "status")
        if type(self.result_entity_refs) is not tuple:
            raise TypeError("result_entity_refs must be an immutable built-in tuple")
        if any(type(reference) is not ResultEntityRef for reference in self.result_entity_refs):
            raise TypeError("result_entity_refs must contain exact ResultEntityRef values")
        if self.error_code is not None and type(self.error_code) is not ErrorCode:
            raise TypeError("error_code must be an ErrorCode or None")
        _strict_utc(self.accepted_at, "accepted_at")
        if self.completed_at is not None:
            _strict_utc(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class CommandReceipt:
    """An immutable receipt row value; persistence remains out of scope."""

    identity: ReceiptIdentity
    request_hash: str
    result: ReceiptResult

    def __post_init__(self) -> None:
        if type(self.identity) is not ReceiptIdentity:
            raise TypeError("identity must be an exact ReceiptIdentity")
        _strict_hash(self.request_hash)
        if type(self.result) is not ReceiptResult:
            raise TypeError("result must be an exact ReceiptResult")


@dataclass(frozen=True, slots=True)
class CommandBinding:
    """Bind a command kind to its frozen idempotency-mismatch identity."""

    command_kind: str
    mismatch_error: ErrorCode

    def __post_init__(self) -> None:
        _strict_nonempty_string(self.command_kind, "command_kind")
        if type(self.mismatch_error) is not ErrorCode:
            raise TypeError("mismatch_error must be an ErrorCode")
        expected = (
            ErrorCode.IDEMPOTENCY_CONFLICT
            if self.command_kind in _SECTION_11_CONFLICT_COMMANDS
            else ErrorCode.IDEMPOTENCY_KEY_REUSE_WITH_DIFFERENT_PAYLOAD
        )
        if self.mismatch_error is not expected:
            raise ValueError("mismatch_error does not match the frozen command binding")

    @classmethod
    def for_command(cls, command_kind: str) -> "CommandBinding":
        """Derive the exact frozen mismatch code for a command kind."""

        _strict_nonempty_string(command_kind, "command_kind")
        mismatch_error = (
            ErrorCode.IDEMPOTENCY_CONFLICT
            if command_kind in _SECTION_11_CONFLICT_COMMANDS
            else ErrorCode.IDEMPOTENCY_KEY_REUSE_WITH_DIFFERENT_PAYLOAD
        )
        return cls(command_kind=command_kind, mismatch_error=mismatch_error)


@dataclass(frozen=True, slots=True)
class ReceiptReplay:
    """A same-identity, same-hash replay of the exact stored result."""

    result: ReceiptResult
    replayed: bool = field(default=True, init=False)

    def __post_init__(self) -> None:
        if type(self.result) is not ReceiptResult:
            raise TypeError("result must be an exact ReceiptResult")


@dataclass(frozen=True, slots=True)
class ReceiptMismatch:
    """A same-identity, different-hash rejection."""

    error_code: ErrorCode

    def __post_init__(self) -> None:
        if type(self.error_code) is not ErrorCode:
            raise TypeError("error_code must be an ErrorCode")
        if self.error_code not in {
            ErrorCode.IDEMPOTENCY_KEY_REUSE_WITH_DIFFERENT_PAYLOAD,
            ErrorCode.IDEMPOTENCY_CONFLICT,
        }:
            raise ValueError("error_code must be a frozen idempotency mismatch code")


def hash_receipt_request(payload: object) -> str:
    """Hash a request with the merged KL-003 canonical JSON/hash scheme."""

    return canonical_sha256(payload)


def decide_receipt_replay(
    *,
    stored: CommandReceipt,
    incoming_identity: ReceiptIdentity,
    incoming_request_hash: str,
    command_binding: CommandBinding,
) -> ReceiptReplay | ReceiptMismatch:
    """Replay an original result or reject a hash mismatch without mutation."""

    if type(stored) is not CommandReceipt:
        raise TypeError("stored must be an exact CommandReceipt")
    if type(incoming_identity) is not ReceiptIdentity:
        raise TypeError("incoming_identity must be an exact ReceiptIdentity")
    incoming_hash = _strict_hash(incoming_request_hash)
    if type(command_binding) is not CommandBinding:
        raise TypeError("command_binding must be an exact CommandBinding")
    if incoming_identity != stored.identity:
        raise ValueError("replay decisions require the same receipt identity")
    if command_binding.command_kind != stored.identity.command_kind:
        raise ValueError("command binding must match the receipt command kind")

    if hmac.compare_digest(stored.request_hash, incoming_hash):
        return ReceiptReplay(result=stored.result)
    return ReceiptMismatch(error_code=command_binding.mismatch_error)
