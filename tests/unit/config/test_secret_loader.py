from __future__ import annotations

import json
import pickle
from dataclasses import asdict, dataclass

import pytest

from kineticloop.config import (
    HEALTHKIT_BRIDGE_CONFIG,
    HEVY_CONFIG,
    MappingSecretSource,
    MissingSecretError,
    ProviderSecrets,
    SecretValue,
    load_provider_secrets,
)

HEVY_SENTINEL = "SYNTHETIC_HEVY_API_KEY_NOT_A_CREDENTIAL"
HEALTHKIT_SENTINEL = "SYNTHETIC_HEALTHKIT_BRIDGE_SECRET_NOT_A_CREDENTIAL"


@dataclass(frozen=True)
class UnsafeGenericContainer:
    value: SecretValue


def test_config_secret_sources_are_separated() -> None:
    public = [asdict(HEVY_CONFIG), asdict(HEALTHKIT_BRIDGE_CONFIG)]
    public_text = json.dumps(public, sort_keys=True)
    assert HEVY_SENTINEL not in public_text
    assert HEALTHKIT_SENTINEL not in public_text
    assert "HEVY_API_KEY" in public_text
    assert "HEALTHKIT_BRIDGE_CLIENT_SECRET" in public_text

    source = MappingSecretSource(
        {
            "HEVY_API_KEY": HEVY_SENTINEL,
            "HEALTHKIT_BRIDGE_CLIENT_SECRET": HEALTHKIT_SENTINEL,
        }
    )
    hevy = load_provider_secrets(HEVY_CONFIG, source)
    healthkit = load_provider_secrets(HEALTHKIT_BRIDGE_CONFIG, source)

    assert hevy.secret("HEVY_API_KEY").reveal() == HEVY_SENTINEL
    assert healthkit.secret("HEALTHKIT_BRIDGE_CLIENT_SECRET").reveal() == HEALTHKIT_SENTINEL
    for rendered in (str(source), repr(source), str(hevy), repr(hevy)):
        assert HEVY_SENTINEL not in rendered
        assert HEALTHKIT_SENTINEL not in rendered

    opaque = hevy.secret("HEVY_API_KEY")
    generic_dataclass = asdict(UnsafeGenericContainer(opaque))
    generic_mapping = {"api_key": opaque}
    assert HEVY_SENTINEL not in str(generic_dataclass)
    assert HEVY_SENTINEL not in repr(generic_mapping)
    with pytest.raises(TypeError):
        json.dumps(generic_dataclass)
    with pytest.raises(TypeError):
        json.dumps(generic_mapping)
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(opaque)
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(generic_dataclass)
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(source)
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(hevy)

    with pytest.raises(TypeError, match="provider_id"):
        ProviderSecrets(123, {"HEVY_API_KEY": opaque})  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="secret names"):
        ProviderSecrets("HEVY", {1: opaque})  # type: ignore[dict-item]
    with pytest.raises(TypeError, match="SecretValue"):
        ProviderSecrets("HEVY", {"HEVY_API_KEY": HEVY_SENTINEL})  # type: ignore[dict-item]

    with pytest.raises(MissingSecretError, match="missing or blank"):
        load_provider_secrets(HEVY_CONFIG, MappingSecretSource({}))
    with pytest.raises(MissingSecretError, match="missing or blank"):
        load_provider_secrets(HEVY_CONFIG, MappingSecretSource({"HEVY_API_KEY": "  "}))
