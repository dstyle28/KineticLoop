from __future__ import annotations

import copy
from pathlib import Path

import pytest

from kineticloop.security.synthetic import (
    SyntheticFixtureError,
    load_synthetic_fixture,
    validate_synthetic_fixture,
)


class EqualSentinel:
    def __eq__(self, other: object) -> bool:
        del other
        return True

    def __repr__(self) -> str:
        return "possibly-real-secret"


def test_synthetic_security_fixtures_have_provenance(tmp_path: Path) -> None:
    root = Path(__file__).parents[2] / "fixtures/synthetic/security"
    fixture_paths = sorted(root.glob("**/*.json"))
    assert fixture_paths

    fixtures = []
    for path in fixture_paths:
        fixtures.append(load_synthetic_fixture(path))

    duplicate_key = tmp_path / "duplicate-key.json"
    duplicate_key.write_text(
        '{"synthetic": true, "synthetic": true}',
        encoding="utf-8",
    )
    with pytest.raises(SyntheticFixtureError, match="duplicate JSON key.*synthetic"):
        load_synthetic_fixture(duplicate_key)

    missing = copy.deepcopy(fixtures[0])
    missing.pop("provenance_id")
    with pytest.raises(SyntheticFixtureError, match="provenance_id"):
        validate_synthetic_fixture(missing)

    production_subject = copy.deepcopy(fixtures[0])
    production_subject["subject"] = {"marker": "PRODUCTION_SUBJECT"}
    with pytest.raises(SyntheticFixtureError, match="non-production"):
        validate_synthetic_fixture(production_subject)

    deceptive_subject = copy.deepcopy(fixtures[0])
    deceptive_subject["subject"]["marker"] = EqualSentinel()
    with pytest.raises(SyntheticFixtureError, match="non-production"):
        validate_synthetic_fixture(deceptive_subject)

    production_provider = copy.deepcopy(fixtures[0])
    production_provider["provider"]["environment"] = "PRODUCTION"
    with pytest.raises(SyntheticFixtureError, match="non-production"):
        validate_synthetic_fixture(production_provider)

    deceptive_environment = copy.deepcopy(fixtures[0])
    deceptive_environment["provider"]["environment"] = EqualSentinel()
    with pytest.raises(SyntheticFixtureError, match="non-production"):
        validate_synthetic_fixture(deceptive_environment)

    undocumented_secret = copy.deepcopy(fixtures[0])
    credential_name = next(iter(undocumented_secret["credentials"]))
    undocumented_secret["credentials"][credential_name] = "possibly-real"
    with pytest.raises(SyntheticFixtureError, match="documented sentinel"):
        validate_synthetic_fixture(undocumented_secret)

    deceptive_credential = copy.deepcopy(fixtures[0])
    credential_name = next(iter(deceptive_credential["credentials"]))
    deceptive_credential["credentials"][credential_name] = EqualSentinel()
    with pytest.raises(SyntheticFixtureError, match="documented sentinel"):
        validate_synthetic_fixture(deceptive_credential)

    deceptive_health = copy.deepcopy(fixtures[0])
    health_name = next(iter(deceptive_health["health_fields"]))
    deceptive_health["health_fields"][health_name] = EqualSentinel()
    with pytest.raises(SyntheticFixtureError, match="documented sentinel"):
        validate_synthetic_fixture(deceptive_health)

    mismatched_identity = copy.deepcopy(fixtures[0])
    mismatched_identity["provenance_id"] = "kineticloop-test-fixture:other-fixture:v1"
    with pytest.raises(SyntheticFixtureError, match="same fixture"):
        validate_synthetic_fixture(mismatched_identity)

    cross_provider = copy.deepcopy(fixtures[0])
    cross_provider["provider"]["id"] = (
        "HEVY_TEST"
        if cross_provider["provider"]["id"] == "HEALTHKIT_BRIDGE_TEST"
        else "HEALTHKIT_BRIDGE_TEST"
    )
    with pytest.raises(SyntheticFixtureError, match="synthetic provider"):
        validate_synthetic_fixture(cross_provider)

    coherent_cross_provider = copy.deepcopy(fixtures[0])
    if coherent_cross_provider["provider"]["id"] == "HEALTHKIT_BRIDGE_TEST":
        coherent_cross_provider["provider"]["id"] = "HEVY_TEST"
        coherent_cross_provider["credentials"] = {
            "HEVY_API_KEY": "SYNTHETIC_HEVY_API_KEY_NOT_A_CREDENTIAL"
        }
        coherent_cross_provider["health_fields"] = {
            "workout_type": "SYNTHETIC_STRENGTH",
            "duration_minutes": 42,
        }
    else:
        coherent_cross_provider["provider"]["id"] = "HEALTHKIT_BRIDGE_TEST"
        coherent_cross_provider["credentials"] = {
            "HEALTHKIT_BRIDGE_CLIENT_SECRET": ("SYNTHETIC_HEALTHKIT_BRIDGE_SECRET_NOT_A_CREDENTIAL")
        }
        coherent_cross_provider["health_fields"] = {
            "resting_heart_rate_bpm": 61,
            "sleep_duration_minutes": 444,
        }
    with pytest.raises(SyntheticFixtureError, match="synthetic provider"):
        validate_synthetic_fixture(coherent_cross_provider)
