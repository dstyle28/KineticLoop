from __future__ import annotations

import dataclasses
import importlib
import json
import socket
from typing import Any

import pytest

from kineticloop.integrations.launch_registry import (
    LAUNCH_SOURCE_SCOPE,
    AIExposurePolicy,
    DegradationPolicy,
    EvidenceDomain,
    LaunchRegistry,
    LaunchRole,
    MissingnessPolicy,
    ProviderCapability,
    Transport,
    WatermarkSemantics,
)
from kineticloop.integrations.provider import (
    ConnectionStatus,
    EvidenceCoverage,
    ProviderId,
    ProviderSourceStatus,
    StreamId,
)


def hostile_replace(value: Any, **changes: Any) -> Any:
    """Submit intentionally ill-typed caller input to the runtime boundary."""
    return dataclasses.replace(value, **changes)


def entry(provider: str, stream: str | None = None) -> ProviderCapability:
    return next(item for item in LAUNCH_SOURCE_SCOPE.entries
                if item.provider_id == provider and (stream is None or item.stream_id == stream))


def test_launch_scope_required_sources() -> None:
    registry = LAUNCH_SOURCE_SCOPE
    assert registry.required_integrations == (ProviderId("APPLE_HEALTHKIT"), ProviderId("HEVY"))
    assert registry.required_fallbacks == (ProviderId("MANUAL_CHAT"),)
    for provider in ("HEVY", "APPLE_HEALTHKIT", "MANUAL_CHAT"):
        with pytest.raises(ValueError):
            dataclasses.replace(registry, entries=tuple(
                item for item in registry.entries if item.provider_id != provider
            ))
        with pytest.raises(ValueError):
            dataclasses.replace(entry(provider), launch_role=LaunchRole.OPTIONAL)


def test_optional_sources_do_not_block_launch() -> None:
    optional = {item.stream_id for item in LAUNCH_SOURCE_SCOPE.entries
                if item.launch_role is LaunchRole.OPTIONAL}
    assert optional == {"OURA_DAILY", "HEALTHKIT_NUTRITION", "MACROFACTOR_EXPORT_IMPORT",
                        "DEXA_FILE_IMPORT"}
    for item in LAUNCH_SOURCE_SCOPE.entries:
        if item.launch_role is LaunchRole.OPTIONAL:
            with pytest.raises(ValueError, match="approved policy/ADR"):
                dataclasses.replace(item, launch_role=LaunchRole.REQUIRED_INTEGRATION)
            assert item.provider_id not in LAUNCH_SOURCE_SCOPE.required_integrations or (
                item.stream_id == "HEALTHKIT_NUTRITION"
            )
    assert "SPREADSHEET" not in LAUNCH_SOURCE_SCOPE.canonical_json()
    assert all(not hasattr(item, "enabled") for item in LAUNCH_SOURCE_SCOPE.entries)


def test_registry_rejects_invalid_duplicate_unknown_entries() -> None:
    registry = LAUNCH_SOURCE_SCOPE
    hevy = entry("HEVY")
    assert type(hevy.provider_id) is ProviderId
    assert type(hevy.stream_id) is StreamId
    for bad in ("HEVY ", "hevy", "", "HEVY__STRENGTH"):
        with pytest.raises(ValueError):
            ProviderId(bad)
        with pytest.raises(ValueError):
            StreamId(bad)
    for changes in (
        {"provider_id": ProviderId("UNKNOWN")}, {"stream_id": StreamId("UNKNOWN")},
        {"provider_id": "HEVY"}, {"stream_id": "HEVY_STRENGTH"},
        {"transport": "public_api"}, {"domains": ("STRENGTH_ACTUALS",)},
        {"domains": [EvidenceDomain.STRENGTH_ACTUALS]},
        {"domains": (EvidenceDomain.STRENGTH_ACTUALS,) * 2},
        {"provenance": ("",)}, {"provenance": ["mutable"]},
        {"provenance": ("same", "same")}, {"exposure_prerequisites": ()},
        {"exposure_prerequisites": hevy.exposure_prerequisites[:1]},
    ):
        with pytest.raises((TypeError, ValueError)):
            dataclasses.replace(hevy, **changes)
    for bad_version in ("1.0.0", "v01.0.0", "v1", "v1.0.0\n", "V1.0.0", 1, None):
        with pytest.raises(ValueError):
            hostile_replace(registry, version=bad_version)
    for entries in ((), list(registry.entries), registry.entries + (hevy,),
                    registry.entries + (dataclasses.replace(hevy, provenance=("different",)),)):
        with pytest.raises(ValueError):
            hostile_replace(registry, entries=entries)
    # A syntactically valid but unknown provider, including retired migration, is still closed.
    for provider in ("SPREADSHEET", "PROVIDER_INJECTED"):
        with pytest.raises(ValueError):
            dataclasses.replace(hevy, provider_id=ProviderId(provider))
    with pytest.raises(TypeError):
        hostile_replace(registry, **{"version": "v1.0.0", "entries": registry.entries,
                          "provider_payload": {"register": "OURA"}})
    assert not hasattr(registry, "register")
    # Revalidation rejects low-level forged nested values at the publication boundary.
    forged = dataclasses.replace(hevy)
    object.__setattr__(forged, "launch_role", LaunchRole.OPTIONAL)
    with pytest.raises(ValueError):
        dataclasses.replace(registry, entries=tuple(
            forged if item.provider_id == "HEVY" else item for item in registry.entries
        ))


def test_registry_version_and_digest_are_deterministic() -> None:
    registry = LAUNCH_SOURCE_SCOPE
    reordered = dataclasses.replace(registry, entries=tuple(
        dataclasses.replace(item, domains=tuple(reversed(item.domains)),
                            provenance=tuple(reversed(item.provenance)),
                            exposure_prerequisites=tuple(reversed(item.exposure_prerequisites)))
        for item in reversed(registry.entries)
    ))
    assert reordered.canonical_json() == registry.canonical_json()
    assert reordered.digest == registry.digest
    assert len(registry.digest) == 71 and registry.digest.startswith("sha256:")
    assert json.loads(registry.canonical_json())["policy_version"] == registry.version
    assert dataclasses.replace(registry, version="v1.0.1").digest != registry.digest
    changed = dataclasses.replace(registry, entries=tuple(
        dataclasses.replace(item, provenance=item.provenance + ("additional revision context",))
        if item.provider_id == "HEVY" else item for item in registry.entries
    ))
    assert changed.digest != registry.digest
    with pytest.raises(dataclasses.FrozenInstanceError):
        registry.version = "v2.0.0"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        entry("HEVY").provenance = ("mutated",)  # type: ignore[misc]
    serialized = json.loads(registry.canonical_json())
    serialized["entries"].clear()
    assert registry.canonical_json() == reordered.canonical_json()


def test_registry_cannot_grant_command_or_fact_authority() -> None:
    registry = LAUNCH_SOURCE_SCOPE
    for item in registry.entries:
        assert item.command_authority == "NONE"
        for authority in ("canonical_fact", "admission", "readiness", "approval", "authorization",
                          "execution", "production_activation", "command_authority"):
            with pytest.raises(TypeError):
                hostile_replace(item, **{authority: "GRANTED"})
    assert EvidenceDomain.STRENGTH_ACTUALS not in entry("APPLE_HEALTHKIT").domains
    assert EvidenceDomain.STRENGTH_ACTUALS not in entry("OURA").domains
    assert EvidenceDomain.PROVIDER_DERIVED_ESTIMATE in entry("MACROFACTOR_EXPORT").domains
    # Registry lookup only returns descriptions; evidence handoff remains KL-055's boundary.
    for method in ("receive_evidence", "admit", "authorize", "execute", "activate"):
        assert not hasattr(registry, method)


def test_oura_ai_exposure_remains_gated() -> None:
    oura = entry("OURA")
    assert oura.ai_exposure is AIExposurePolicy.DENIED_PENDING_INT_06
    assert {str(item) for item in oura.exposure_prerequisites} >= {
        "APPROVED_INTEGRATION_LANE", "DOCUMENTED_CONSENT_SCOPES", "RETENTION_AND_DELETION_POLICY",
        "THIRD_PARTY_AI_TERMS_REVIEW", "EXACT_MODEL_FIELD_ALLOWLIST",
    }
    # Policy applies to raw and derived content alike, without an availability/connection override.
    assert EvidenceDomain.PROVIDER_DERIVED_ESTIMATE in oura.domains
    with pytest.raises(ValueError):
        dataclasses.replace(oura, ai_exposure=AIExposurePolicy.ADMITTED_FACTS_THROUGH_CONTEXT_POLICY)
    for flag in ("connected", "available", "ai_enabled", "compliance_approved", "derived_only"):
        with pytest.raises(TypeError):
            hostile_replace(oura, **{flag: True})
    assert dataclasses.replace(LAUNCH_SOURCE_SCOPE, version="v2.0.0").entries == (
        LAUNCH_SOURCE_SCOPE.entries
    )


def test_scope_membership_is_not_health_coverage_or_launch_ready() -> None:
    registry = LAUNCH_SOURCE_SCOPE
    for coverage in (EvidenceCoverage.PARTIAL, EvidenceCoverage.UNKNOWN):
        status = ProviderSourceStatus(
            schema_version="kineticloop-provider-source-status-v1",
            provider_id=ProviderId("APPLE_HEALTHKIT"), stream_id=StreamId("HEALTHKIT_HEALTH_ACTIVITY"),
            connection_status=ConnectionStatus.CONNECTED, coverage=coverage,
            last_success_at=None, last_attempt_at=None, source_watermark=None,
            coverage_start=None, coverage_end=None, partial_scope_or_permission_ambiguity=True,
            last_error_code=None,
        )
        assert status.coverage is coverage
        assert status.source_watermark is None
        assert registry.required_integrations == ("APPLE_HEALTHKIT", "HEVY")
    healthkit = entry("APPLE_HEALTHKIT")
    assert healthkit.missingness is MissingnessPolicy.NO_VISIBLE_SAMPLES_UNKNOWN_CAUSE
    assert healthkit.degradation is (
        DegradationPolicy.HISTORY_AND_SUBJECTIVE_IF_PLANNING_POLICY_PERMITS
    )
    assert entry("HEVY").degradation is (
        DegradationPolicy.MANUAL_ACTUALS_NO_WEARABLE_SET_INFERENCE
    )
    assert entry("OURA").degradation is (
        DegradationPolicy.REDUCED_RECOVERY_COMPLETENESS_SAME_SOURCE_BASELINES
    )
    assert entry("HEVY").watermark is WatermarkSemantics.PROVIDER_EVENT_CURSOR
    assert healthkit.watermark is WatermarkSemantics.PER_TYPE_QUERY_SCOPE_ANCHOR
    assert entry("MACROFACTOR_EXPORT").transport is Transport.CONTROLLED_FILE_IMPORT
    for item in registry.entries:
        for runtime_fact in ("connection_status", "coverage", "launch_ready", "enabled", "active"):
            assert not hasattr(item, runtime_fact)
            with pytest.raises(TypeError):
                hostile_replace(item, **{runtime_fact: True})


def test_registry_is_hermetic(monkeypatch: pytest.MonkeyPatch) -> None:
    import os
    import subprocess

    import psycopg

    import kineticloop.integrations.launch_registry as module

    original = LAUNCH_SOURCE_SCOPE.canonical_json()
    original_namespace = dict(vars(module))

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("ambient/network/database/process access forbidden")

    class NoEnvironment(dict[str, str]):
        __getitem__ = forbidden
        get = forbidden
        __iter__ = forbidden

    monkeypatch.setattr(os, "environ", NoEnvironment())
    monkeypatch.setattr(os, "getenv", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(psycopg, "connect", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    try:
        reloaded = importlib.reload(module)
        assert reloaded.LAUNCH_SOURCE_SCOPE.canonical_json() == original
        assert reloaded.LAUNCH_SOURCE_SCOPE.digest.startswith("sha256:")
        assert reloaded.LAUNCH_SOURCE_SCOPE.required_integrations == ("APPLE_HEALTHKIT", "HEVY")
    finally:
        # Preserve canonical class identities for later tests in the same interpreter.
        module.__dict__.update(original_namespace)
