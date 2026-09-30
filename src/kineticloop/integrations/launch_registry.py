"""Trusted descriptive launch policy; no runtime state or authority is granted."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, fields
from enum import StrEnum
from hashlib import sha256

from kineticloop.integrations.provider import ProviderId, StreamId


class LaunchRole(StrEnum):
    REQUIRED_INTEGRATION = "REQUIRED_INTEGRATION"
    REQUIRED_FALLBACK = "REQUIRED_FALLBACK"
    OPTIONAL = "OPTIONAL"


class EvidenceDomain(StrEnum):
    SUBJECTIVE = "SUBJECTIVE"
    CORRECTION = "CORRECTION"
    STRENGTH_ACTUALS = "STRENGTH_ACTUALS"
    EXERCISE_IDENTITY = "EXERCISE_IDENTITY"
    SLEEP = "SLEEP"
    HEART_RATE = "HEART_RATE"
    HRV = "HRV"
    RESTING_HEART_RATE = "RESTING_HEART_RATE"
    ACTIVITY = "ACTIVITY"
    CARDIO = "CARDIO"
    WEIGHT = "WEIGHT"
    NUTRITION = "NUTRITION"
    PROVIDER_DERIVED_ESTIMATE = "PROVIDER_DERIVED_ESTIMATE"
    BODY_COMPOSITION = "BODY_COMPOSITION"


class Transport(StrEnum):
    AUTHENTICATED_APP = "AUTHENTICATED_APP"
    PUBLIC_API = "PUBLIC_API"
    IOS_BRIDGE = "IOS_BRIDGE"
    OAUTH_API_OR_APPROVED_MCP = "OAUTH_API_OR_APPROVED_MCP"
    CONTROLLED_FILE_IMPORT = "CONTROLLED_FILE_IMPORT"


class IncrementalSemantics(StrEnum):
    EXPLICIT_REPORT_REVISION = "EXPLICIT_REPORT_REVISION"
    WORKOUT_UPDATE_DELETE_POLLING = "WORKOUT_UPDATE_DELETE_POLLING"
    OBSERVER_THEN_ANCHORED_ADD_DELETE = "OBSERVER_THEN_ANCHORED_ADD_DELETE"
    PER_STREAM_POLLING_RECONCILIATION = "PER_STREAM_POLLING_RECONCILIATION"
    IMMUTABLE_IMPORT_REVISION = "IMMUTABLE_IMPORT_REVISION"


class WatermarkSemantics(StrEnum):
    REPORT_REVISION = "REPORT_REVISION"
    PROVIDER_EVENT_CURSOR = "PROVIDER_EVENT_CURSOR"
    PER_TYPE_QUERY_SCOPE_ANCHOR = "PER_TYPE_QUERY_SCOPE_ANCHOR"
    PER_STREAM_DATE_OR_CURSOR = "PER_STREAM_DATE_OR_CURSOR"
    IMPORT_IDENTITY_AND_HASH = "IMPORT_IDENTITY_AND_HASH"


class MissingnessPolicy(StrEnum):
    UNKNOWN_OR_PARTIAL_NEVER_ZERO_OR_STALE = "UNKNOWN_OR_PARTIAL_NEVER_ZERO_OR_STALE"
    NO_VISIBLE_SAMPLES_UNKNOWN_CAUSE = "NO_VISIBLE_SAMPLES_UNKNOWN_CAUSE"


class DegradationPolicy(StrEnum):
    OTHER_EVIDENCE_AMBIGUITY_UNRESOLVED = "OTHER_EVIDENCE_AMBIGUITY_UNRESOLVED"
    MANUAL_ACTUALS_NO_WEARABLE_SET_INFERENCE = "MANUAL_ACTUALS_NO_WEARABLE_SET_INFERENCE"
    HISTORY_AND_SUBJECTIVE_IF_PLANNING_POLICY_PERMITS = (
        "HISTORY_AND_SUBJECTIVE_IF_PLANNING_POLICY_PERMITS"
    )
    REDUCED_RECOVERY_COMPLETENESS_SAME_SOURCE_BASELINES = (
        "REDUCED_RECOVERY_COMPLETENESS_SAME_SOURCE_BASELINES"
    )
    OTHER_NUTRITION_OR_MANUAL_IMPORT = "OTHER_NUTRITION_OR_MANUAL_IMPORT"
    NO_BODY_COMPOSITION_CONCLUSION = "NO_BODY_COMPOSITION_CONCLUSION"


class AIExposurePolicy(StrEnum):
    ADMITTED_FACTS_THROUGH_CONTEXT_POLICY = "ADMITTED_FACTS_THROUGH_CONTEXT_POLICY"
    DENIED_PENDING_INT_06 = "DENIED_PENDING_INT_06"


class ExposurePrerequisite(StrEnum):
    ACTION_SCOPED_ADMISSION = "ACTION_SCOPED_ADMISSION"
    CONSENT_AND_CONTEXT_FIELD_POLICY = "CONSENT_AND_CONTEXT_FIELD_POLICY"
    APPROVED_INTEGRATION_LANE = "APPROVED_INTEGRATION_LANE"
    DOCUMENTED_CONSENT_SCOPES = "DOCUMENTED_CONSENT_SCOPES"
    RETENTION_AND_DELETION_POLICY = "RETENTION_AND_DELETION_POLICY"
    THIRD_PARTY_AI_TERMS_REVIEW = "THIRD_PARTY_AI_TERMS_REVIEW"
    EXACT_MODEL_FIELD_ALLOWLIST = "EXACT_MODEL_FIELD_ALLOWLIST"


_COMMON_EXPOSURE = (
    ExposurePrerequisite.ACTION_SCOPED_ADMISSION,
    ExposurePrerequisite.CONSENT_AND_CONTEXT_FIELD_POLICY,
)
_OURA_EXPOSURE = _COMMON_EXPOSURE + (
    ExposurePrerequisite.APPROVED_INTEGRATION_LANE,
    ExposurePrerequisite.DOCUMENTED_CONSENT_SCOPES,
    ExposurePrerequisite.RETENTION_AND_DELETION_POLICY,
    ExposurePrerequisite.THIRD_PARTY_AI_TERMS_REVIEW,
    ExposurePrerequisite.EXACT_MODEL_FIELD_ALLOWLIST,
)
# Closed source catalog, including an optional stream of the mandatory HealthKit provider.
_CATALOG = (
    ("MANUAL_CHAT", "MANUAL_CHAT_REPORT", LaunchRole.REQUIRED_FALLBACK),
    ("HEVY", "HEVY_STRENGTH", LaunchRole.REQUIRED_INTEGRATION),
    ("APPLE_HEALTHKIT", "HEALTHKIT_HEALTH_ACTIVITY", LaunchRole.REQUIRED_INTEGRATION),
    ("APPLE_HEALTHKIT", "HEALTHKIT_NUTRITION", LaunchRole.OPTIONAL),
    ("OURA", "OURA_DAILY", LaunchRole.OPTIONAL),
    ("MACROFACTOR_EXPORT", "MACROFACTOR_EXPORT_IMPORT", LaunchRole.OPTIONAL),
    ("DEXA_FILE", "DEXA_FILE_IMPORT", LaunchRole.OPTIONAL),
)


def _unique_tuple(value: object, item_type: type[object]) -> None:
    if type(value) is not tuple or not value:
        raise ValueError("metadata must be a nonempty immutable tuple")
    if any(type(item) is not item_type for item in value) or len(set(value)) != len(value):
        raise ValueError("metadata has invalid or duplicate members")


@dataclass(frozen=True, slots=True)
class ProviderCapability:
    """Evidence description only; never a command capability or exposure approval."""

    provider_id: ProviderId
    stream_id: StreamId
    launch_role: LaunchRole
    domains: tuple[EvidenceDomain, ...]
    transport: Transport
    incremental: IncrementalSemantics
    watermark: WatermarkSemantics
    provenance: tuple[str, ...]
    missingness: MissingnessPolicy
    degradation: DegradationPolicy
    ai_exposure: AIExposurePolicy
    exposure_prerequisites: tuple[ExposurePrerequisite, ...]

    def __post_init__(self) -> None:
        for name, expected in (
            ("provider_id", ProviderId), ("stream_id", StreamId), ("launch_role", LaunchRole),
            ("transport", Transport), ("incremental", IncrementalSemantics),
            ("watermark", WatermarkSemantics), ("missingness", MissingnessPolicy),
            ("degradation", DegradationPolicy), ("ai_exposure", AIExposurePolicy),
        ):
            if type(getattr(self, name)) is not expected:
                raise ValueError(f"invalid canonical {name}")
        if (self.provider_id, self.stream_id, self.launch_role) not in _CATALOG:
            raise ValueError("unknown source or changed launch role requires approved policy/ADR")
        _unique_tuple(self.domains, EvidenceDomain)
        _unique_tuple(self.provenance, str)
        if any(not item.strip() or len(item) > 160 for item in self.provenance):
            raise ValueError("provenance descriptions must be bounded and nonblank")
        _unique_tuple(self.exposure_prerequisites, ExposurePrerequisite)
        expected_exposure = _OURA_EXPOSURE if self.provider_id == "OURA" else _COMMON_EXPOSURE
        if set(self.exposure_prerequisites) != set(expected_exposure):
            raise ValueError("exposure prerequisites cannot be bypassed")
        expected_policy = (
            AIExposurePolicy.DENIED_PENDING_INT_06 if self.provider_id == "OURA"
            else AIExposurePolicy.ADMITTED_FACTS_THROUGH_CONTEXT_POLICY
        )
        if self.ai_exposure is not expected_policy:
            raise ValueError("AI exposure policy cannot be enabled by caller flags")

    @property
    def command_authority(self) -> str:
        return "NONE"

    def canonical_value(self) -> dict[str, object]:
        value: dict[str, object] = {}
        for field in fields(self):
            member = getattr(self, field.name)
            value[field.name] = sorted(str(item) for item in member) if isinstance(member, tuple) \
                else str(member)
        value["command_authority"] = "NONE"
        return value


@dataclass(frozen=True, slots=True)
class LaunchRegistry:
    """Explicit trusted policy value. No provider registration or runtime update API."""

    version: str
    entries: tuple[ProviderCapability, ...]

    def __post_init__(self) -> None:
        if type(self.version) is not str or re.fullmatch(
            r"v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", self.version
        ) is None:
            raise ValueError("registry version must be canonical vMAJOR.MINOR.PATCH")
        _unique_tuple(self.entries, ProviderCapability)
        # Revalidate even dataclass values forged by low-level construction before publishing.
        for entry in self.entries:
            entry.__post_init__()
        identities = [(entry.provider_id, entry.stream_id) for entry in self.entries]
        if len(set(identities)) != len(identities):
            raise ValueError("duplicate source identity")
        if set(identities) != {(provider, stream) for provider, stream, _ in _CATALOG}:
            raise ValueError("registry must publish exactly the closed launch source catalog")
        object.__setattr__(self, "entries", tuple(sorted(
            self.entries, key=lambda entry: (entry.provider_id, entry.stream_id)
        )))

    @property
    def required_integrations(self) -> tuple[ProviderId, ...]:
        return tuple(entry.provider_id for entry in self.entries
                     if entry.launch_role is LaunchRole.REQUIRED_INTEGRATION)

    @property
    def required_fallbacks(self) -> tuple[ProviderId, ...]:
        return tuple(entry.provider_id for entry in self.entries
                     if entry.launch_role is LaunchRole.REQUIRED_FALLBACK)

    def canonical_json(self) -> str:
        return json.dumps({
            "schema_version": "kineticloop-launch-registry-v1",
            "policy_version": self.version,
            "entries": [entry.canonical_value() for entry in self.entries],
        }, sort_keys=True, ensure_ascii=False, separators=(",", ":"))

    @property
    def digest(self) -> str:
        return "sha256:" + sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _capability(
    provider: str, stream: str, role: LaunchRole, domains: tuple[EvidenceDomain, ...],
    transport: Transport, incremental: IncrementalSemantics, watermark: WatermarkSemantics,
    provenance: tuple[str, ...], degradation: DegradationPolicy,
) -> ProviderCapability:
    return ProviderCapability(
        provider_id=ProviderId(provider), stream_id=StreamId(stream), launch_role=role,
        domains=domains, transport=transport, incremental=incremental, watermark=watermark,
        provenance=provenance,
        missingness=(MissingnessPolicy.NO_VISIBLE_SAMPLES_UNKNOWN_CAUSE
                    if provider == "APPLE_HEALTHKIT"
                    else MissingnessPolicy.UNKNOWN_OR_PARTIAL_NEVER_ZERO_OR_STALE),
        degradation=degradation,
        ai_exposure=(AIExposurePolicy.DENIED_PENDING_INT_06 if provider == "OURA"
                     else AIExposurePolicy.ADMITTED_FACTS_THROUGH_CONTEXT_POLICY),
        exposure_prerequisites=_OURA_EXPOSURE if provider == "OURA" else _COMMON_EXPOSURE,
    )


LAUNCH_SOURCE_SCOPE = LaunchRegistry(version="v1.0.0", entries=(
    _capability(
        "MANUAL_CHAT", "MANUAL_CHAT_REPORT", LaunchRole.REQUIRED_FALLBACK,
        (EvidenceDomain.SUBJECTIVE, EvidenceDomain.CORRECTION, EvidenceDomain.STRENGTH_ACTUALS,
         EvidenceDomain.CARDIO, EvidenceDomain.WEIGHT, EvidenceDomain.NUTRITION),
        Transport.AUTHENTICATED_APP, IncrementalSemantics.EXPLICIT_REPORT_REVISION,
        WatermarkSemantics.REPORT_REVISION, ("authenticated report identity", "user reported"),
        DegradationPolicy.OTHER_EVIDENCE_AMBIGUITY_UNRESOLVED,
    ),
    _capability(
        "HEVY", "HEVY_STRENGTH", LaunchRole.REQUIRED_INTEGRATION,
        (EvidenceDomain.STRENGTH_ACTUALS, EvidenceDomain.EXERCISE_IDENTITY,
         EvidenceDomain.CARDIO, EvidenceDomain.WEIGHT),
        Transport.PUBLIC_API, IncrementalSemantics.WORKOUT_UPDATE_DELETE_POLLING,
        WatermarkSemantics.PROVIDER_EVENT_CURSOR,
        ("workout and exercise template identity", "update/delete revision", "mapping version"),
        DegradationPolicy.MANUAL_ACTUALS_NO_WEARABLE_SET_INFERENCE,
    ),
    _capability(
        "APPLE_HEALTHKIT", "HEALTHKIT_HEALTH_ACTIVITY", LaunchRole.REQUIRED_INTEGRATION,
        (EvidenceDomain.SLEEP, EvidenceDomain.HEART_RATE, EvidenceDomain.HRV,
         EvidenceDomain.RESTING_HEART_RATE, EvidenceDomain.ACTIVITY, EvidenceDomain.CARDIO,
         EvidenceDomain.WEIGHT),
        Transport.IOS_BRIDGE, IncrementalSemantics.OBSERVER_THEN_ANCHORED_ADD_DELETE,
        WatermarkSemantics.PER_TYPE_QUERY_SCOPE_ANCHOR,
        ("HealthKit UUID and sample type", "sourceRevision and device when available",
         "bridge upload identity and deletion event"),
        DegradationPolicy.HISTORY_AND_SUBJECTIVE_IF_PLANNING_POLICY_PERMITS,
    ),
    _capability(
        "APPLE_HEALTHKIT", "HEALTHKIT_NUTRITION", LaunchRole.OPTIONAL,
        (EvidenceDomain.NUTRITION,), Transport.IOS_BRIDGE,
        IncrementalSemantics.OBSERVER_THEN_ANCHORED_ADD_DELETE,
        WatermarkSemantics.PER_TYPE_QUERY_SCOPE_ANCHOR,
        ("HealthKit UUID and sample type", "sourceRevision and upstream app identity"),
        DegradationPolicy.OTHER_NUTRITION_OR_MANUAL_IMPORT,
    ),
    _capability(
        "OURA", "OURA_DAILY", LaunchRole.OPTIONAL,
        (EvidenceDomain.SLEEP, EvidenceDomain.HEART_RATE, EvidenceDomain.ACTIVITY,
         EvidenceDomain.CARDIO, EvidenceDomain.PROVIDER_DERIVED_ESTIMATE),
        Transport.OAUTH_API_OR_APPROVED_MCP, IncrementalSemantics.PER_STREAM_POLLING_RECONCILIATION,
        WatermarkSemantics.PER_STREAM_DATE_OR_CURSOR,
        ("Oura observation identity", "provider derived summaries retain Oura lineage"),
        DegradationPolicy.REDUCED_RECOVERY_COMPLETENESS_SAME_SOURCE_BASELINES,
    ),
    _capability(
        "MACROFACTOR_EXPORT", "MACROFACTOR_EXPORT_IMPORT", LaunchRole.OPTIONAL,
        (EvidenceDomain.NUTRITION, EvidenceDomain.WEIGHT, EvidenceDomain.PROVIDER_DERIVED_ESTIMATE),
        Transport.CONTROLLED_FILE_IMPORT, IncrementalSemantics.IMMUTABLE_IMPORT_REVISION,
        WatermarkSemantics.IMPORT_IDENTITY_AND_HASH,
        ("immutable export hash and row identity", "expenditure and weight trend are estimates"),
        DegradationPolicy.OTHER_NUTRITION_OR_MANUAL_IMPORT,
    ),
    _capability(
        "DEXA_FILE", "DEXA_FILE_IMPORT", LaunchRole.OPTIONAL,
        (EvidenceDomain.BODY_COMPOSITION,), Transport.CONTROLLED_FILE_IMPORT,
        IncrementalSemantics.IMMUTABLE_IMPORT_REVISION, WatermarkSemantics.IMPORT_IDENTITY_AND_HASH,
        ("immutable report hash", "extraction page/span provenance"),
        DegradationPolicy.NO_BODY_COMPOSITION_CONCLUSION,
    ),
))
