from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest
from pydantic import ValidationError

from kineticloop.config.secrets import (
    MappingSecretSource,
    PublicProviderConfig,
    load_provider_secrets,
)
from kineticloop.integrations.provider import (
    AcquisitionMethod,
    ConnectionStatus,
    EvidenceCoverage,
    EvidenceEnvelope,
    EvidenceLineage,
    ProviderContractError,
    ProviderId,
    ProviderSourceStatus,
    RawProviderObservation,
    SourceClass,
    StreamId,
    SubjectMismatchError,
    TrustClass,
    TrustedProviderBinding,
    build_evidence_envelope,
    create_provider_context,
    parse_evidence_envelope_json,
    safe_adapter_failure,
    validate_adapter_output,
    validate_receive_evidence_binding,
)
from kineticloop.security.synthetic import load_synthetic_fixture

SUBJECT_ID = "11111111-1111-4111-8111-111111111111"
FOREIGN_SUBJECT_ID = "22222222-2222-4222-8222-222222222222"
SOURCE_CONNECTION_ID = "33333333-3333-4333-8333-333333333333"
FOREIGN_SOURCE_CONNECTION_ID = "44444444-4444-4444-8444-444444444444"
NOW = "2026-09-26T12:30:00.000000Z"
OBSERVED = "2026-09-26T12:00:00.000000Z"
SECRET = "SYNTHETIC_HEVY_API_KEY_NOT_A_CREDENTIAL"


def binding() -> TrustedProviderBinding:
    return TrustedProviderBinding(
        schema_version="kineticloop-provider-binding-v1",
        subject_id=SUBJECT_ID,
        provider_id=ProviderId("HEVY"),
        stream_id=StreamId("HEVY_STRENGTH"),
        source_connection_id=SOURCE_CONNECTION_ID,
        source_class=SourceClass.PROVIDER_STRUCTURED,
        trust_class=TrustClass.PROVIDER_REPORTED,
        adapter_version="hevy-adapter-v1",
    )


def context(*, endpoint: str = "https://api.hevyapp.com/v1") -> Any:
    config = PublicProviderConfig(
        provider_id="HEVY",
        endpoint=endpoint,
        required_secret_names=("HEVY_API_KEY",),
    )
    secrets = load_provider_secrets(
        config,
        MappingSecretSource({"HEVY_API_KEY": SECRET}),
    )
    return create_provider_context(binding(), config, secrets)


def observation(*, payload: Any = None) -> RawProviderObservation:
    if payload is None:
        payload = {"workout_id": "synthetic-workout-1", "sets": 3}
    return RawProviderObservation(
        schema_version="kineticloop-provider-observation-v1",
        source_object_type="workout",
        source_object_id="synthetic-workout-1",
        provider_revision="revision-1",
        stable_observation_key=None,
        observed_at=OBSERVED,
        effective_at=OBSERVED,
        payload=payload,
        controlled_blob_reference=None,
        lineage=EvidenceLineage(
            schema_version="kineticloop-evidence-lineage-v1",
            root_provider_id=ProviderId("HEVY"),
            acquisition_method=AcquisitionMethod.DIRECT_PROVIDER_API,
            upstream_object_ids=("synthetic-workout-1",),
            forwarded=False,
        ),
        content_schema_version="hevy-workout-v1",
    )


def envelope() -> EvidenceEnvelope:
    return build_evidence_envelope(context(), observation(), server_now=lambda: NOW)


def test_provider_and_stream_ids_are_canonical() -> None:
    assert ProviderId("HEVY") == "HEVY"
    assert StreamId("HEVY_STRENGTH") == "HEVY_STRENGTH"
    for token in ("hevy", "HEVY-APP", " HEVY", "HEVY__APP", "", "A" * 65):
        with pytest.raises((TypeError, ValueError)):
            ProviderId(token)
    for token in ("hevy_strength", "HEVY/STRENGTH", "HEVY__STRENGTH", ""):
        with pytest.raises((TypeError, ValueError)):
            StreamId(token)
    with pytest.raises(TypeError):
        ProviderId(1)  # type: ignore[arg-type]


def test_provider_subject_source_binding_is_trusted() -> None:
    with pytest.raises(ValidationError):
        RawProviderObservation.model_validate(
            observation().model_dump(mode="python")
            | {"subject_id": FOREIGN_SUBJECT_ID, "source_connection_id": FOREIGN_SOURCE_CONNECTION_ID}
        )

    built = envelope()
    assert built.subject_id == SUBJECT_ID
    assert built.source_connection_id == SOURCE_CONNECTION_ID
    validate_receive_evidence_binding(
        built,
        binding(),
        command_subject_id=SUBJECT_ID,
        command_source_connection_id=SOURCE_CONNECTION_ID,
    )

    for command_subject, command_source in (
        (FOREIGN_SUBJECT_ID, SOURCE_CONNECTION_ID),
        (SUBJECT_ID, FOREIGN_SOURCE_CONNECTION_ID),
    ):
        with pytest.raises(SubjectMismatchError) as captured:
            validate_receive_evidence_binding(
                built,
                binding(),
                command_subject_id=command_subject,
                command_source_connection_id=command_source,
            )
        assert str(captured.value) == "provider contract rejected: SUBJECT_MISMATCH; provider=UNKNOWN"
        assert FOREIGN_SUBJECT_ID not in str(captured.value)
        assert FOREIGN_SOURCE_CONNECTION_ID not in str(captured.value)

    foreign_envelope = built.model_copy(update={"subject_id": FOREIGN_SUBJECT_ID})
    with pytest.raises(SubjectMismatchError):
        validate_receive_evidence_binding(
            foreign_envelope,
            binding(),
            command_subject_id=SUBJECT_ID,
            command_source_connection_id=SOURCE_CONNECTION_ID,
        )


def test_evidence_provenance_and_times_required() -> None:
    raw = observation().model_dump(mode="python")
    for required in ("lineage", "observed_at", "effective_at"):
        malformed = raw.copy()
        malformed.pop(required)
        with pytest.raises(ValidationError):
            RawProviderObservation.model_validate(malformed)

    evidence = envelope().model_dump(mode="python")
    evidence.pop("known_at")
    with pytest.raises(ValidationError):
        EvidenceEnvelope.model_validate(evidence)

    noncanonical = raw | {"observed_at": "2026-09-26T12:00:00Z"}
    with pytest.raises(ValidationError, match="canonical UTC"):
        RawProviderObservation.model_validate(noncanonical)


def test_evidence_envelope_closed_s09_schema() -> None:
    evidence = envelope()
    expected = {
        "schema_version",
        "subject_id",
        "provider_id",
        "stream_id",
        "source_connection_id",
        "source_object_type",
        "source_object_id",
        "provider_revision",
        "stable_observation_key",
        "observed_at",
        "effective_at",
        "known_at",
        "payload_hash",
        "controlled_blob_reference",
        "hash_scheme_version",
        "source_class",
        "trust_class",
        "lineage",
        "content_schema_version",
        "adapter_version",
        "command_authority",
    }
    dumped = evidence.model_dump(mode="json")
    assert set(dumped) == expected
    assert dumped["command_authority"] == "NONE"
    assert "payload" not in dumped
    assert parse_evidence_envelope_json(evidence.to_canonical_json()) == evidence

    for forbidden in (
        "canonical_fact",
        "command",
        "approval",
        "capability",
        "authorization",
        "progression_pointer",
        "readiness_verdict",
    ):
        with pytest.raises(ValidationError):
            EvidenceEnvelope.model_validate(dumped | {forbidden: "FORGED"})

    missing = dumped.copy()
    missing.pop("lineage")
    with pytest.raises(ValidationError):
        EvidenceEnvelope.model_validate(missing)

    duplicated = '{"subject_id":"' + SUBJECT_ID + '",' + json.dumps(dumped)[1:]
    with pytest.raises(ProviderContractError, match="DUPLICATE_FIELD"):
        parse_evidence_envelope_json(duplicated)

    both_identities = observation().model_dump(mode="python") | {
        "stable_observation_key": "observation-1"
    }
    with pytest.raises(ValidationError, match="exactly one provider revision"):
        RawProviderObservation.model_validate(both_identities)


def test_server_assigns_known_at() -> None:
    with pytest.raises(ValidationError):
        RawProviderObservation.model_validate(
            observation().model_dump(mode="python") | {"known_at": "1999-01-01T00:00:00.000000Z"}
        )
    built = build_evidence_envelope(context(), observation(), server_now=lambda: NOW)
    assert built.known_at == NOW
    assert built.observed_at == OBSERVED


def test_provider_has_no_fact_or_command_authority() -> None:
    built = envelope()
    assert built.command_authority == "NONE"
    assert validate_adapter_output((built,)) == (built,)
    for forged in (
        {"canonical_fact": True},
        {"command_kind": "AdvanceProgression"},
        {"approval": "APPROVED"},
        {"authorization": "AUTHORIZED"},
    ):
        with pytest.raises(ProviderContractError, match="ADAPTER_OUTPUT_NOT_EVIDENCE"):
            validate_adapter_output((forged,))
    with pytest.raises(ValidationError):
        EvidenceEnvelope.model_validate(
            built.model_dump(mode="python") | {"command_authority": "PROVIDER"}
        )


def test_provider_credentials_do_not_cross_evidence_or_diagnostic_boundary(
    caplog: pytest.LogCaptureFixture,
) -> None:
    encoded = quote(SECRET, safe="")
    for endpoint in (
        f"https://synthetic:{SECRET}@provider.invalid/v1",
        f"https://provider.invalid/v1?api_key={SECRET}",
        f"https://provider.invalid/v1?api_key={encoded}",
    ):
        with pytest.raises(ProviderContractError) as captured:
            context(endpoint=endpoint)
        assert SECRET not in str(captured.value)
        assert encoded not in str(captured.value)

    for payload in (
        {"nested": {"api_key": SECRET}},
        {"nested": [f"token={SECRET}"]},
        {"nested": [encoded]},
        {"url": f"https://synthetic:{SECRET}@provider.invalid/workout"},
    ):
        with pytest.raises(ProviderContractError) as captured:
            build_evidence_envelope(context(), observation(payload=payload), server_now=lambda: NOW)
        assert SECRET not in str(captured.value)
        assert encoded not in str(captured.value)

    provider_context = context()
    assert SECRET not in repr(provider_context)
    assert SECRET not in str(provider_context)
    assert SECRET not in repr(provider_context.credential_guard)
    safe_failure = safe_adapter_failure(provider_context, RuntimeError("provider timeout"))
    assert safe_failure.code == "ADAPTER_FAILURE_RUNTIMEERROR"
    assert "HEVY" in str(safe_failure)
    assert "timeout" not in str(safe_failure)
    with pytest.raises(ProviderContractError) as captured:
        safe_adapter_failure(provider_context, RuntimeError(f"failed api_key={encoded}"))
    assert SECRET not in str(captured.value)
    assert encoded not in str(captured.value)

    built = envelope()
    representations = (
        built.to_canonical_json(),
        str(built),
        repr(built),
        caplog.text,
        str(safe_failure),
        repr(safe_failure),
    )
    assert all(SECRET not in item and encoded not in item for item in representations)
    evidence_root = Path(__file__).parents[3] / "docs/exec-plans/evidence/KL-055"
    if evidence_root.exists():
        assert all(SECRET not in path.read_text(encoding="utf-8") for path in evidence_root.rglob("*") if path.is_file())


def test_transport_health_differs_from_coverage() -> None:
    connected_partial = ProviderSourceStatus(
        schema_version="kineticloop-provider-source-status-v1",
        provider_id=ProviderId("HEVY"),
        stream_id=StreamId("HEVY_STRENGTH"),
        connection_status=ConnectionStatus.CONNECTED,
        coverage=EvidenceCoverage.PARTIAL,
        last_success_at=NOW,
        last_attempt_at=NOW,
        source_watermark="provider-cursor-17",
        coverage_start=OBSERVED,
        coverage_end=NOW,
        partial_scope_or_permission_ambiguity=True,
        last_error_code=None,
    )
    assert connected_partial.connection_status is ConnectionStatus.CONNECTED
    assert connected_partial.coverage is EvidenceCoverage.PARTIAL
    assert connected_partial.partial_scope_or_permission_ambiguity is True


def test_provider_contract_is_hermetic(tmp_path: Path) -> None:
    script = tmp_path / "hermetic_provider_contract.py"
    script.write_text(
        """
import os
import socket

def denied(*args, **kwargs):
    raise AssertionError("network access denied")

socket.socket = denied
socket.create_connection = denied
assert not any(name.startswith(("HEVY_", "OURA_", "HEALTHKIT_")) for name in os.environ)

from kineticloop.config.secrets import MappingSecretSource, PublicProviderConfig, load_provider_secrets
from kineticloop.integrations.provider import (
    AcquisitionMethod, EvidenceLineage, ProviderId, RawProviderObservation,
    SourceClass, StreamId, TrustClass, TrustedProviderBinding,
    build_evidence_envelope, create_provider_context,
)

config = PublicProviderConfig("HEVY", "https://provider.invalid/v1", ("HEVY_API_KEY",))
secrets = load_provider_secrets(config, MappingSecretSource({
    "HEVY_API_KEY": "SYNTHETIC_HEVY_API_KEY_NOT_A_CREDENTIAL"
}))
binding = TrustedProviderBinding(
    schema_version="kineticloop-provider-binding-v1",
    subject_id="11111111-1111-4111-8111-111111111111",
    provider_id=ProviderId("HEVY"), stream_id=StreamId("HEVY_STRENGTH"),
    source_connection_id="33333333-3333-4333-8333-333333333333",
    source_class=SourceClass.PROVIDER_STRUCTURED,
    trust_class=TrustClass.PROVIDER_REPORTED, adapter_version="hevy-adapter-v1",
)
observation = RawProviderObservation(
    schema_version="kineticloop-provider-observation-v1", source_object_type="workout",
    source_object_id="synthetic-workout-1", provider_revision="revision-1",
    stable_observation_key=None, observed_at="2026-09-26T12:00:00.000000Z",
    effective_at="2026-09-26T12:00:00.000000Z", payload={"sets": 3},
    controlled_blob_reference=None,
    lineage=EvidenceLineage(
        schema_version="kineticloop-evidence-lineage-v1", root_provider_id=ProviderId("HEVY"),
        acquisition_method=AcquisitionMethod.DIRECT_PROVIDER_API,
        upstream_object_ids=("synthetic-workout-1",), forwarded=False,
    ), content_schema_version="hevy-workout-v1",
)
context = create_provider_context(binding, config, secrets)
first = build_evidence_envelope(
    context, observation, server_now=lambda: "2026-09-26T12:30:00.000000Z"
)
second = build_evidence_envelope(
    context, observation, server_now=lambda: "2026-09-26T12:30:00.000000Z"
)
assert first.to_canonical_json() == second.to_canonical_json()
print("HERMETIC_PROVIDER_PASS")
""".strip(),
        encoding="utf-8",
    )
    clean_env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONHASHSEED": "0",
        "PYTHONPATH": str(Path(__file__).parents[3] / "src"),
    }
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=Path(__file__).parents[3],
        env=clean_env,
        check=True,
        text=True,
        capture_output=True,
    )
    assert result.stdout.strip() == "HERMETIC_PROVIDER_PASS"
    assert result.stderr == ""


def test_provider_fixtures_pass_hardened_synthetic_guard() -> None:
    root = Path(__file__).parents[2] / "fixtures/synthetic/providers"
    paths = sorted(root.rglob("*.json"))
    assert paths
    for path in paths:
        fixture = load_synthetic_fixture(path)
        assert fixture["synthetic"] is True
        assert fixture["subject"] == {"marker": "NON_PRODUCTION_TEST_SUBJECT"}
        assert fixture["provider"]["environment"] == "SYNTHETIC_TEST"
        assert fixture["provider"]["id"].endswith("_TEST")


def test_synthetic_provider_fixtures_pass() -> None:
    root = Path(__file__).parents[2] / "fixtures/synthetic/providers"
    fixtures = [load_synthetic_fixture(path) for path in sorted(root.rglob("*.json"))]
    assert fixtures
    assert {item["provider"]["id"] for item in fixtures} == {"HEVY_TEST"}
    assert len({item["provenance_id"] for item in fixtures}) == len(fixtures)
