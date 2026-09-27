"""Provider transport contracts that terminate at immutable S09 evidence.

The types in this module deliberately stop before Evidence Admission.  An adapter
may describe what a provider returned, but it cannot publish a canonical fact or
invoke a command owner other than ``EvidenceService.ReceiveEvidence``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Protocol, SupportsIndex, cast
from urllib.parse import unquote

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from pydantic_core import core_schema

from kineticloop.config.secrets import ProviderSecrets, PublicProviderConfig
from kineticloop.primitives import canonical_json, canonical_sha256, canonical_utc
from kineticloop.security.redaction import Redactor

_CANONICAL_UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PROVIDER_ID = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*$")
_STREAM_ID = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*$")
_OBJECT_TYPE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
_VERSION = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_SENSITIVE_KEY = re.compile(
    r"(?:^|[_ .-])(?:access[_ .-]?token|api[_ .-]?key|authorization|client[_ .-]?secret|"
    r"cookie|credential(?:s)?|password|refresh[_ .-]?token|secret|token)(?:$|[_ .-])",
    re.IGNORECASE,
)
_MAX_PERCENT_DECODE = 4

type JsonScalar = None | bool | int | str
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]


class ProviderContractError(ValueError):
    """A fail-closed provider boundary error with credential-safe text."""

    def __init__(self, code: str, *, provider_id: str | None = None) -> None:
        safe_provider = provider_id if provider_id and _PROVIDER_ID.fullmatch(provider_id) else "UNKNOWN"
        super().__init__(f"provider contract rejected: {code}; provider={safe_provider}")
        self.code = code
        self.provider_id = safe_provider


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, member in pairs:
        if key in value:
            raise ProviderContractError("DUPLICATE_FIELD")
        value[key] = member
    return value


class SubjectMismatchError(ProviderContractError):
    """Non-enumerating mismatch used at the ReceiveEvidence handoff."""

    def __init__(self) -> None:
        super().__init__("SUBJECT_MISMATCH")


class _CanonicalToken(str):
    pattern: re.Pattern[str]
    label: str
    max_length: int

    def __new__(cls, value: str) -> _CanonicalToken:
        if type(value) is cls:
            return cast(_CanonicalToken, value)
        if type(value) is not str:
            raise TypeError(f"{cls.label} must be a string")
        if len(value) > cls.max_length or cls.pattern.fullmatch(value) is None:
            raise ValueError(f"{cls.label} is not canonical")
        return cast(_CanonicalToken, str.__new__(cls, value))

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: Any
    ) -> core_schema.CoreSchema:
        del source_type, handler
        return core_schema.no_info_plain_validator_function(
            cls,
            serialization=core_schema.plain_serializer_function_ser_schema(str),
        )


class ProviderId(_CanonicalToken):
    """Canonical, stable provider identity (for example ``HEVY``)."""

    pattern = _PROVIDER_ID
    label = "provider_id"
    max_length = 64


class StreamId(_CanonicalToken):
    """Canonical provider stream identity (for example ``HEVY_STRENGTH``)."""

    pattern = _STREAM_ID
    label = "stream_id"
    max_length = 96


def _canonical_uuid(value: object, label: str) -> str:
    if type(value) is not str or _CANONICAL_UUID.fullmatch(value) is None:
        raise ValueError(f"{label} must be a canonical UUID")
    return value


def _canonical_hash(value: object, label: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lower-case SHA-256 digest")
    return value


def _canonical_version(value: object, label: str) -> str:
    if type(value) is not str or _VERSION.fullmatch(value) is None:
        raise ValueError(f"{label} must be a canonical version token")
    return value


def _canonical_time(value: object, label: str) -> str:
    if type(value) is not str or canonical_utc(value) != value:
        raise ValueError(f"{label} must be canonical UTC")
    return value


class SourceClass(StrEnum):
    PROVIDER_STRUCTURED = "PROVIDER_STRUCTURED"
    PROVIDER_FREE_TEXT = "PROVIDER_FREE_TEXT"
    DEVICE_BRIDGE = "DEVICE_BRIDGE"
    FILE_IMPORT = "FILE_IMPORT"


class TrustClass(StrEnum):
    PROVIDER_REPORTED = "PROVIDER_REPORTED"
    DEVICE_REPORTED = "DEVICE_REPORTED"
    USER_REPORTED = "USER_REPORTED"
    UNTRUSTED_TEXT = "UNTRUSTED_TEXT"


class AcquisitionMethod(StrEnum):
    DIRECT_PROVIDER_API = "DIRECT_PROVIDER_API"
    DEVICE_BRIDGE = "DEVICE_BRIDGE"
    CONTROLLED_IMPORT = "CONTROLLED_IMPORT"


class ConnectionStatus(StrEnum):
    UNCONFIGURED = "UNCONFIGURED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    CONNECTED = "CONNECTED"
    DEGRADED = "DEGRADED"
    REAUTH_REQUIRED = "REAUTH_REQUIRED"
    DISABLED = "DISABLED"


class EvidenceCoverage(StrEnum):
    COMPLETE_THROUGH_WATERMARK = "COMPLETE_THROUGH_WATERMARK"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE_PROVIDER_DISABLED = "UNAVAILABLE_PROVIDER_DISABLED"


class EvidenceLineage(BaseModel):
    """Closed lineage carried with, but unable to elevate, provider evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["kineticloop-evidence-lineage-v1"]
    root_provider_id: ProviderId
    acquisition_method: AcquisitionMethod
    upstream_object_ids: tuple[str, ...]
    forwarded: bool

    @model_validator(mode="after")
    def stable_upstream_identities(self) -> EvidenceLineage:
        if any(type(item) is not str or not item.strip() for item in self.upstream_object_ids):
            raise ValueError("lineage identities must be non-blank strings")
        if len(set(self.upstream_object_ids)) != len(self.upstream_object_ids):
            raise ValueError("lineage identities must be unique")
        return self


class TrustedProviderBinding(BaseModel):
    """Server-side registry result; never populated from provider payload fields."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["kineticloop-provider-binding-v1"]
    subject_id: str
    provider_id: ProviderId
    stream_id: StreamId
    source_connection_id: str
    source_class: SourceClass
    trust_class: TrustClass
    adapter_version: str

    @model_validator(mode="after")
    def canonical_binding(self) -> TrustedProviderBinding:
        _canonical_uuid(self.subject_id, "subject_id")
        _canonical_uuid(self.source_connection_id, "source_connection_id")
        _canonical_version(self.adapter_version, "adapter_version")
        return self


class RawProviderObservation(BaseModel):
    """Provider-owned fields accepted before the trusted binding is attached."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["kineticloop-provider-observation-v1"]
    source_object_type: str
    source_object_id: str
    provider_revision: str | None
    stable_observation_key: str | None
    observed_at: str
    effective_at: str
    payload: JsonValue | None
    controlled_blob_reference: str | None
    lineage: EvidenceLineage
    content_schema_version: str

    @model_validator(mode="after")
    def closed_observation(self) -> RawProviderObservation:
        if type(self.source_object_type) is not str or _OBJECT_TYPE.fullmatch(
            self.source_object_type
        ) is None:
            raise ValueError("source_object_type is not canonical")
        if type(self.source_object_id) is not str or not self.source_object_id.strip():
            raise ValueError("source_object_id must be non-blank")
        for label, value in (
            ("provider_revision", self.provider_revision),
            ("stable_observation_key", self.stable_observation_key),
        ):
            if value is not None and (type(value) is not str or not value.strip()):
                raise ValueError(f"{label} must be non-blank when present")
        if (self.provider_revision is None) == (self.stable_observation_key is None):
            raise ValueError("exactly one provider revision or stable observation key is required")
        _canonical_time(self.observed_at, "observed_at")
        _canonical_time(self.effective_at, "effective_at")
        _canonical_version(self.content_schema_version, "content_schema_version")
        if (self.payload is None) == (self.controlled_blob_reference is None):
            raise ValueError("exactly one payload or controlled blob reference is required")
        if self.controlled_blob_reference is not None and (
            type(self.controlled_blob_reference) is not str
            or not self.controlled_blob_reference.startswith("blob://")
            or len(self.controlled_blob_reference) > 256
        ):
            raise ValueError("controlled_blob_reference is not canonical")
        return self


class EvidenceEnvelope(BaseModel):
    """Strict S09 transport envelope; it carries evidence and no authority."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["kineticloop-evidence-envelope-v1"]
    subject_id: str
    provider_id: ProviderId
    stream_id: StreamId
    source_connection_id: str
    source_object_type: str
    source_object_id: str
    provider_revision: str | None
    stable_observation_key: str | None
    observed_at: str
    effective_at: str
    known_at: str
    payload_hash: str | None
    controlled_blob_reference: str | None
    hash_scheme_version: Literal["sha256-kineticloop-json-v1"]
    source_class: SourceClass
    trust_class: TrustClass
    lineage: EvidenceLineage
    content_schema_version: str
    adapter_version: str
    command_authority: Literal["NONE"]

    @model_validator(mode="after")
    def closed_s09_shape(self) -> EvidenceEnvelope:
        _canonical_uuid(self.subject_id, "subject_id")
        _canonical_uuid(self.source_connection_id, "source_connection_id")
        if _OBJECT_TYPE.fullmatch(self.source_object_type) is None:
            raise ValueError("source_object_type is not canonical")
        if not self.source_object_id.strip():
            raise ValueError("source_object_id must be non-blank")
        if (self.provider_revision is None) == (self.stable_observation_key is None):
            raise ValueError("exactly one provider revision or stable observation key is required")
        _canonical_time(self.observed_at, "observed_at")
        _canonical_time(self.effective_at, "effective_at")
        _canonical_time(self.known_at, "known_at")
        if (self.payload_hash is None) == (self.controlled_blob_reference is None):
            raise ValueError("exactly one payload hash or controlled blob reference is required")
        if self.payload_hash is not None:
            _canonical_hash(self.payload_hash, "payload_hash")
        if self.controlled_blob_reference is not None and not self.controlled_blob_reference.startswith(
            "blob://"
        ):
            raise ValueError("controlled_blob_reference is not canonical")
        _canonical_version(self.content_schema_version, "content_schema_version")
        _canonical_version(self.adapter_version, "adapter_version")
        return self

    def to_canonical_json(self) -> str:
        return canonical_json(self.model_dump(mode="json"))


class ProviderSourceStatus(BaseModel):
    """Transport lifecycle and evidence coverage remain separate dimensions."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["kineticloop-provider-source-status-v1"]
    provider_id: ProviderId
    stream_id: StreamId
    connection_status: ConnectionStatus
    coverage: EvidenceCoverage
    last_success_at: str | None
    last_attempt_at: str | None
    source_watermark: str | None
    coverage_start: str | None
    coverage_end: str | None
    partial_scope_or_permission_ambiguity: bool
    last_error_code: str | None

    @model_validator(mode="after")
    def canonical_status_times(self) -> ProviderSourceStatus:
        for label in ("last_success_at", "last_attempt_at", "coverage_start", "coverage_end"):
            value = getattr(self, label)
            if value is not None:
                _canonical_time(value, label)
        return self


class ProviderBatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["kineticloop-provider-batch-v1"]
    stream_id: StreamId
    cursor: str | None
    observations: tuple[RawProviderObservation, ...]


class BackfillResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["kineticloop-provider-backfill-result-v1"]
    batches: tuple[ProviderBatch, ...]


class ReconciliationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["kineticloop-provider-reconciliation-result-v1"]
    observations: tuple[RawProviderObservation, ...]
    corrections_detected: int = Field(ge=0)


class TimeWindow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    start: str
    end: str

    @model_validator(mode="after")
    def canonical_window(self) -> TimeWindow:
        _canonical_time(self.start, "start")
        _canonical_time(self.end, "end")
        if self.start >= self.end:
            raise ValueError("time window must be non-empty")
        return self


class ProviderAdapter(Protocol):
    """Hermetic adapter boundary from provider transport to evidence only."""

    provider: ProviderId
    streams: tuple[StreamId, ...]

    async def connection_status(self) -> ProviderSourceStatus: ...

    async def initial_backfill(self) -> BackfillResult: ...

    async def fetch_incremental(self, cursor: str | None) -> ProviderBatch: ...

    async def reconcile(self, window: TimeWindow) -> ReconciliationResult: ...

    def normalize(self, batch: ProviderBatch) -> tuple[EvidenceEnvelope, ...]: ...


def parse_evidence_envelope_json(value: str) -> EvidenceEnvelope:
    """Parse one envelope while rejecting duplicate JSON members."""

    if type(value) is not str:
        raise TypeError("evidence envelope JSON must be a string")
    malformed = False
    payload: object | None = None
    try:
        payload = json.loads(value, object_pairs_hook=_reject_duplicate_json_keys)
    except ProviderContractError:
        raise
    except (UnicodeError, json.JSONDecodeError):
        malformed = True
    if malformed or payload is None:
        raise ProviderContractError("INVALID_ENVELOPE_JSON")
    invalid = False
    parsed: EvidenceEnvelope | None = None
    try:
        parsed = EvidenceEnvelope.model_validate_json(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        )
    except (TypeError, ValueError, ValidationError):
        invalid = True
    if invalid or parsed is None:
        raise ProviderContractError("INVALID_EVIDENCE_ENVELOPE")
    return parsed


def _revalidate_evidence_envelope(value: object) -> EvidenceEnvelope:
    if type(value) is not EvidenceEnvelope:
        raise ProviderContractError("ADAPTER_OUTPUT_NOT_EVIDENCE")
    envelope = cast(EvidenceEnvelope, value)
    if set(envelope.__dict__) != set(EvidenceEnvelope.model_fields):
        raise ProviderContractError("INVALID_EVIDENCE_ENVELOPE")
    if envelope.__pydantic_extra__:
        raise ProviderContractError("INVALID_EVIDENCE_ENVELOPE")

    invalid = False
    validated: EvidenceEnvelope | None = None
    raw: dict[str, Any] | None = None
    try:
        raw = envelope.model_dump(mode="json", warnings="error")
        validated = EvidenceEnvelope.model_validate_json(
            json.dumps(raw, ensure_ascii=False, separators=(",", ":"))
        )
    except (TypeError, ValueError, ValidationError):
        invalid = True
    if invalid or validated is None or raw is None:
        raise ProviderContractError("INVALID_EVIDENCE_ENVELOPE")
    if validated.to_canonical_json() != canonical_json(raw):
        raise ProviderContractError("INVALID_EVIDENCE_ENVELOPE")
    return validated


def validate_adapter_output(
    context: ProviderExecutionContext, value: object
) -> tuple[EvidenceEnvelope, ...]:
    """Revalidate, bind, and credential-scan every adapter evidence output."""

    if type(value) is not tuple:
        raise ProviderContractError("ADAPTER_OUTPUT_NOT_EVIDENCE")
    validated: list[EvidenceEnvelope] = []
    for item in cast(tuple[object, ...], value):
        envelope = _revalidate_evidence_envelope(item)
        validate_receive_evidence_binding(
            envelope,
            context.binding,
            command_subject_id=context.binding.subject_id,
            command_source_connection_id=context.binding.source_connection_id,
        )
        context.credential_guard.reject_credentials(
            envelope.model_dump(mode="json"), provider_id=str(context.binding.provider_id)
        )
        validated.append(envelope)
    return tuple(validated)


def _decoded_forms(value: str) -> tuple[str, ...]:
    forms = [value]
    current = value
    for _ in range(_MAX_PERCENT_DECODE):
        decoded = unquote(current)
        if decoded == current:
            break
        forms.append(decoded)
        current = decoded
    return tuple(forms)


def _walk(value: object, *, depth: int = 0) -> Sequence[tuple[str | None, str]]:
    if depth > 32:
        raise ProviderContractError("CREDENTIAL_BOUNDARY")
    found: list[tuple[str | None, str]] = []
    if type(value) is str:
        found.append((None, value))
    elif type(value) is bytes:
        found.append((None, value.decode("utf-8", errors="replace")))
    elif type(value) is dict:
        for key, member in cast(dict[object, object], value).items():
            key_text = key if type(key) is str else "<non-string-key>"
            if _SENSITIVE_KEY.search(key_text):
                raise ProviderContractError("CREDENTIAL_BOUNDARY")
            if type(member) is str:
                found.append((key_text, member))
            else:
                found.extend(_walk(member, depth=depth + 1))
    elif type(value) in (list, tuple):
        for member in cast(list[object] | tuple[object, ...], value):
            found.extend(_walk(member, depth=depth + 1))
    elif isinstance(value, BaseException):
        found.extend(_walk(tuple(value.args), depth=depth + 1))
        if value.__cause__ is not None:
            found.extend(_walk(value.__cause__, depth=depth + 1))
        if value.__context__ is not None and value.__context__ is not value.__cause__:
            found.extend(_walk(value.__context__, depth=depth + 1))
    return found


class CredentialGuard:
    """Bounded scanner for credentials known to the explicit provider context."""

    __slots__ = ("__registered_values",)

    def __init__(self, registered_values: tuple[str, ...]) -> None:
        if any(type(value) is not str or not value for value in registered_values):
            raise TypeError("registered credentials must be non-blank strings")
        self.__registered_values = registered_values

    def __init_subclass__(cls, **kwargs: object) -> None:
        del cls, kwargs
        raise TypeError("CredentialGuard cannot be subclassed")

    @classmethod
    def from_provider_secrets(cls, secrets: ProviderSecrets) -> CredentialGuard:
        values = tuple(secrets.secret(name).reveal() for name in secrets.names)
        return cls(values)

    def __repr__(self) -> str:
        return "CredentialGuard(<redacted>)"

    def __str__(self) -> str:
        return "CredentialGuard(<redacted>)"

    def __reduce__(self) -> str | tuple[Any, ...]:
        raise TypeError("CredentialGuard cannot be serialized")

    def __reduce_ex__(self, protocol: SupportsIndex) -> str | tuple[Any, ...]:
        del protocol
        raise TypeError("CredentialGuard cannot be serialized")

    def __getstate__(self) -> object:
        raise TypeError("CredentialGuard cannot be serialized")

    def reject_credentials(self, value: object, *, provider_id: str | None = None) -> None:
        for key, text in _walk(value):
            forms = _decoded_forms(text)
            if key is not None and _SENSITIVE_KEY.search(key):
                raise ProviderContractError("CREDENTIAL_BOUNDARY", provider_id=provider_id)
            for form in forms:
                if any(secret in form for secret in self.__registered_values):
                    raise ProviderContractError("CREDENTIAL_BOUNDARY", provider_id=provider_id)
                lowered = form.casefold()
                if "authorization:" in lowered or "authorization=" in lowered:
                    raise ProviderContractError("CREDENTIAL_BOUNDARY", provider_id=provider_id)
                if re.search(r"[a-z][a-z0-9+.-]*://[^/@\s]+:[^/@\s]+@", form, re.I):
                    raise ProviderContractError("CREDENTIAL_BOUNDARY", provider_id=provider_id)
                if re.search(
                    r"(?:access[_ .-]?token|api[_ .-]?key|client[_ .-]?secret|password|"
                    r"refresh[_ .-]?token|secret|token)\s*[=:]",
                    form,
                    re.I,
                ):
                    raise ProviderContractError("CREDENTIAL_BOUNDARY", provider_id=provider_id)


class ProviderExecutionContext:
    """Explicit provider context; no ambient environment or network lookup occurs."""

    __slots__ = ("__binding", "__credential_guard", "__public_config", "__redactor")

    def __init__(
        self,
        *,
        binding: TrustedProviderBinding,
        public_config: PublicProviderConfig,
        credential_guard: CredentialGuard,
        redactor: Redactor,
    ) -> None:
        self.__binding = binding
        self.__public_config = public_config
        self.__credential_guard = credential_guard
        self.__redactor = redactor

    def __init_subclass__(cls, **kwargs: object) -> None:
        del cls, kwargs
        raise TypeError("ProviderExecutionContext cannot be subclassed")

    @property
    def binding(self) -> TrustedProviderBinding:
        return self.__binding

    @property
    def public_config(self) -> PublicProviderConfig:
        return self.__public_config

    @property
    def credential_guard(self) -> CredentialGuard:
        return self.__credential_guard

    def __repr__(self) -> str:
        return f"ProviderExecutionContext(provider_id={self.binding.provider_id!s})"

    def __str__(self) -> str:
        return repr(self)

    def safe_diagnostic(self, value: object) -> object:
        return self.__redactor.redact(value)

    def __reduce__(self) -> str | tuple[Any, ...]:
        raise TypeError("ProviderExecutionContext cannot be serialized")

    def __reduce_ex__(self, protocol: SupportsIndex) -> str | tuple[Any, ...]:
        del protocol
        raise TypeError("ProviderExecutionContext cannot be serialized")

    def __getstate__(self) -> object:
        raise TypeError("ProviderExecutionContext cannot be serialized")


def create_provider_context(
    binding: TrustedProviderBinding,
    public_config: PublicProviderConfig,
    secrets: ProviderSecrets,
) -> ProviderExecutionContext:
    """Build an explicit credential-safe context without reading ambient state."""

    provider_id = str(binding.provider_id)
    guard = CredentialGuard.from_provider_secrets(secrets)
    if public_config.provider_id != provider_id or secrets.provider_id != provider_id:
        raise ProviderContractError("PROVIDER_IDENTITY_MISMATCH", provider_id=provider_id)
    guard.reject_credentials(
        {
            "provider_id": public_config.provider_id,
            "endpoint": public_config.endpoint,
            "required_secret_names": list(public_config.required_secret_names),
        },
        provider_id=provider_id,
    )
    return ProviderExecutionContext(
        binding=binding,
        public_config=public_config,
        credential_guard=guard,
        redactor=Redactor(
            secrets=tuple(secrets.secret(name) for name in secrets.names)
        ),
    )


def build_evidence_envelope(
    context: ProviderExecutionContext,
    observation: RawProviderObservation,
    *,
    server_now: Callable[[], datetime | str],
) -> EvidenceEnvelope:
    """Attach the trusted binding and server time to provider-owned observation data."""

    provider_id = str(context.binding.provider_id)
    if observation.lineage.root_provider_id != context.binding.provider_id:
        raise ProviderContractError("LINEAGE_PROVIDER_MISMATCH", provider_id=provider_id)
    context.credential_guard.reject_credentials(
        observation.model_dump(mode="python"), provider_id=provider_id
    )
    invalid_time = False
    known_at: str | None = None
    try:
        known_at = canonical_utc(server_now())
    except Exception:
        invalid_time = True
    if invalid_time or known_at is None:
        raise ProviderContractError("SERVER_TIME_UNAVAILABLE", provider_id=provider_id)
    payload_hash = canonical_sha256(observation.payload) if observation.payload is not None else None
    envelope = EvidenceEnvelope(
        schema_version="kineticloop-evidence-envelope-v1",
        subject_id=context.binding.subject_id,
        provider_id=context.binding.provider_id,
        stream_id=context.binding.stream_id,
        source_connection_id=context.binding.source_connection_id,
        source_object_type=observation.source_object_type,
        source_object_id=observation.source_object_id,
        provider_revision=observation.provider_revision,
        stable_observation_key=observation.stable_observation_key,
        observed_at=observation.observed_at,
        effective_at=observation.effective_at,
        known_at=known_at,
        payload_hash=payload_hash,
        controlled_blob_reference=observation.controlled_blob_reference,
        hash_scheme_version="sha256-kineticloop-json-v1",
        source_class=context.binding.source_class,
        trust_class=context.binding.trust_class,
        lineage=observation.lineage,
        content_schema_version=observation.content_schema_version,
        adapter_version=context.binding.adapter_version,
        command_authority="NONE",
    )
    context.credential_guard.reject_credentials(envelope.model_dump(mode="json"), provider_id=provider_id)
    return envelope


def validate_receive_evidence_binding(
    envelope: EvidenceEnvelope,
    binding: TrustedProviderBinding,
    *,
    command_subject_id: str,
    command_source_connection_id: str,
) -> None:
    """Validate the owner handoff with one non-enumerating mismatch result."""

    envelope = _revalidate_evidence_envelope(envelope)
    expected = (
        binding.subject_id,
        str(binding.provider_id),
        str(binding.stream_id),
        binding.source_connection_id,
    )
    received = (
        envelope.subject_id,
        str(envelope.provider_id),
        str(envelope.stream_id),
        envelope.source_connection_id,
    )
    command = (command_subject_id, command_source_connection_id)
    if received != expected or command != (binding.subject_id, binding.source_connection_id):
        raise SubjectMismatchError()


def safe_adapter_failure(context: ProviderExecutionContext, error: BaseException) -> ProviderContractError:
    """Return a fixed safe failure while retaining provider and failure class context."""

    context.credential_guard.reject_credentials(error, provider_id=str(context.binding.provider_id))
    failure_class = type(error).__name__
    context.credential_guard.reject_credentials(
        failure_class, provider_id=str(context.binding.provider_id)
    )
    safe = context.safe_diagnostic(error)
    del safe
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", failure_class) is None:
        failure_class = "UNKNOWN"
    return ProviderContractError(
        f"ADAPTER_FAILURE_{failure_class.upper()}", provider_id=str(context.binding.provider_id)
    )


__all__ = [
    "AcquisitionMethod",
    "BackfillResult",
    "ConnectionStatus",
    "CredentialGuard",
    "EvidenceCoverage",
    "EvidenceEnvelope",
    "EvidenceLineage",
    "ProviderAdapter",
    "ProviderBatch",
    "ProviderContractError",
    "ProviderExecutionContext",
    "ProviderId",
    "ProviderSourceStatus",
    "RawProviderObservation",
    "ReconciliationResult",
    "SourceClass",
    "StreamId",
    "SubjectMismatchError",
    "TimeWindow",
    "TrustClass",
    "TrustedProviderBinding",
    "build_evidence_envelope",
    "create_provider_context",
    "parse_evidence_envelope_json",
    "safe_adapter_failure",
    "validate_adapter_output",
    "validate_receive_evidence_binding",
]
