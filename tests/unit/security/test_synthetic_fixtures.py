from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from kineticloop.security.synthetic import SyntheticFixtureError, validate_synthetic_fixture


def test_synthetic_security_fixtures_have_provenance() -> None:
    root = Path(__file__).parents[2] / "fixtures/synthetic/security"
    fixture_paths = sorted(root.glob("**/*.json"))
    assert fixture_paths

    fixtures = []
    for path in fixture_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        validate_synthetic_fixture(payload)
        fixtures.append(payload)

    missing = copy.deepcopy(fixtures[0])
    missing.pop("provenance_id")
    with pytest.raises(SyntheticFixtureError, match="provenance_id"):
        validate_synthetic_fixture(missing)

    production_subject = copy.deepcopy(fixtures[0])
    production_subject["subject"] = {"marker": "PRODUCTION_SUBJECT"}
    with pytest.raises(SyntheticFixtureError, match="non-production"):
        validate_synthetic_fixture(production_subject)

    production_provider = copy.deepcopy(fixtures[0])
    production_provider["provider"]["environment"] = "PRODUCTION"
    with pytest.raises(SyntheticFixtureError, match="non-production"):
        validate_synthetic_fixture(production_provider)

    undocumented_secret = copy.deepcopy(fixtures[0])
    undocumented_secret["credentials"]["HEVY_API_KEY"] = "possibly-real"
    with pytest.raises(SyntheticFixtureError, match="documented sentinel"):
        validate_synthetic_fixture(undocumented_secret)
