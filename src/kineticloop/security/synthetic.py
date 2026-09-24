"""Validation for committed security fixtures that can never claim production provenance."""

from __future__ import annotations

import re
from collections.abc import Mapping

_FIXTURE_ID = re.compile(r"^synthetic-security-(?P<name>[a-z0-9-]+)-v(?P<version>[0-9]+)$")
_PROVENANCE_ID = re.compile(r"^kineticloop-test-fixture:(?P<name>[a-z0-9-]+):v(?P<version>[0-9]+)$")
_PROVIDERS = {"HEVY_TEST", "HEALTHKIT_BRIDGE_TEST"}

SYNTHETIC_SENTINEL_SECRETS = {
    "HEVY_API_KEY": "SYNTHETIC_HEVY_API_KEY_NOT_A_CREDENTIAL",
    "HEALTHKIT_BRIDGE_CLIENT_SECRET": "SYNTHETIC_HEALTHKIT_BRIDGE_SECRET_NOT_A_CREDENTIAL",
}

SYNTHETIC_HEALTH_SENTINELS: dict[str, object] = {
    "workout_type": "SYNTHETIC_STRENGTH",
    "duration_minutes": 42,
    "resting_heart_rate_bpm": 61,
    "sleep_duration_minutes": 444,
}

_PROVIDER_FIELDS = {
    "HEVY_TEST": {
        "credentials": {"HEVY_API_KEY"},
        "health_fields": {"workout_type", "duration_minutes"},
    },
    "HEALTHKIT_BRIDGE_TEST": {
        "credentials": {"HEALTHKIT_BRIDGE_CLIENT_SECRET"},
        "health_fields": {"resting_heart_rate_bpm", "sleep_duration_minutes"},
    },
}


class SyntheticFixtureError(ValueError):
    """Fixture provenance or sentinel content is unsafe or malformed."""


def _require_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise SyntheticFixtureError(f"{label} must be an object")
    return value


def validate_synthetic_fixture(payload: object) -> None:
    """Fail closed unless the fixture is marked, non-production, and sentinel-only."""

    fixture = _require_mapping(payload, "fixture")
    if fixture.get("synthetic") is not True:
        raise SyntheticFixtureError("fixture must be explicitly marked synthetic")

    fixture_id = fixture.get("fixture_id")
    provenance_id = fixture.get("provenance_id")
    fixture_match = _FIXTURE_ID.fullmatch(fixture_id) if isinstance(fixture_id, str) else None
    provenance_match = (
        _PROVENANCE_ID.fullmatch(provenance_id) if isinstance(provenance_id, str) else None
    )
    if fixture_match is None:
        raise SyntheticFixtureError("fixture_id is missing or unstable")
    if provenance_match is None:
        raise SyntheticFixtureError("provenance_id is missing or unstable")
    if fixture_match.groups() != provenance_match.groups():
        raise SyntheticFixtureError("fixture_id and provenance_id must identify the same fixture")

    subject = _require_mapping(fixture.get("subject"), "subject")
    if subject != {"marker": "NON_PRODUCTION_TEST_SUBJECT"}:
        raise SyntheticFixtureError("fixture subject must be the non-production test marker")

    provider = _require_mapping(fixture.get("provider"), "provider")
    provider_id = provider.get("id")
    if (
        not isinstance(provider_id, str)
        or provider_id not in _PROVIDERS
        or provider.get("environment") != "SYNTHETIC_TEST"
    ):
        raise SyntheticFixtureError("fixture provider must be explicitly non-production")
    if set(provider) != {"id", "environment"}:
        raise SyntheticFixtureError("fixture provider has undocumented fields")

    credentials = _require_mapping(fixture.get("credentials"), "credentials")
    profile = _PROVIDER_FIELDS[provider_id]
    if set(credentials) != profile["credentials"]:
        raise SyntheticFixtureError("credentials do not match the synthetic provider profile")
    for name, value in credentials.items():
        if SYNTHETIC_SENTINEL_SECRETS.get(name) != value:
            raise SyntheticFixtureError(f"credential {name!r} is not a documented sentinel")

    health_fields = _require_mapping(fixture.get("health_fields"), "health_fields")
    if set(health_fields) != profile["health_fields"]:
        raise SyntheticFixtureError("health_fields do not match the synthetic provider profile")
    for name, value in health_fields.items():
        if SYNTHETIC_HEALTH_SENTINELS.get(name) != value:
            raise SyntheticFixtureError(f"health field {name!r} is not a documented sentinel")

    if set(fixture) != {
        "synthetic",
        "fixture_id",
        "provenance_id",
        "subject",
        "provider",
        "credentials",
        "health_fields",
    }:
        raise SyntheticFixtureError("fixture has undocumented top-level fields")
