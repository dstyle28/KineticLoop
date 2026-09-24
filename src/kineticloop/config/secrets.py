"""Keep public provider configuration separate from explicitly supplied secrets."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

_HIDDEN = "<secret>"


class MissingSecretError(ValueError):
    """A required secret was absent or blank in the selected secret source."""


class SecretValue:
    """An opaque value that reveals itself only through an explicit in-process call.

    It deliberately has no JSON or mapping serialization protocol. Generic dataclass
    copying may retain the object, but its string and representation stay redacted.
    """

    __slots__ = ("__value",)

    def __init__(self, value: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise MissingSecretError("secret values must be non-blank strings")
        self.__value = value

    def reveal(self) -> str:
        """Return the value for the explicit in-process consumer only."""

        return self.__value

    def __str__(self) -> str:
        return _HIDDEN

    def __repr__(self) -> str:
        return "SecretValue(<secret>)"

    def __deepcopy__(self, memo: dict[int, object]) -> SecretValue:
        del memo
        return self


class SecretSource(Protocol):
    """Explicit source selected by the caller; never an implicit environment read."""

    def get_secret(self, name: str) -> str | None: ...


class MappingSecretSource:
    """In-memory source used by tests and caller-controlled secret-store adapters."""

    __slots__ = ("__values",)

    def __init__(self, values: Mapping[str, str]) -> None:
        self.__values = dict(values)

    def get_secret(self, name: str) -> str | None:
        return self.__values.get(name)

    def __str__(self) -> str:
        return "MappingSecretSource(<redacted>)"

    def __repr__(self) -> str:
        return "MappingSecretSource(<redacted>)"


@dataclass(frozen=True)
class PublicProviderConfig:
    """Serializable provider metadata containing names, never credential values."""

    provider_id: str
    endpoint: str
    required_secret_names: tuple[str, ...]


HEVY_CONFIG = PublicProviderConfig(
    provider_id="HEVY",
    endpoint="https://api.hevyapp.com/v1",
    required_secret_names=("HEVY_API_KEY",),
)

HEALTHKIT_BRIDGE_CONFIG = PublicProviderConfig(
    provider_id="HEALTHKIT_BRIDGE",
    endpoint="https://healthkit-bridge.invalid/v1",
    required_secret_names=("HEALTHKIT_BRIDGE_CLIENT_SECRET",),
)


class ProviderSecrets:
    """Loaded secret bundle with no generic iteration or serialization surface."""

    __slots__ = ("__provider_id", "__values")

    def __init__(self, provider_id: str, values: Mapping[str, SecretValue]) -> None:
        self.__provider_id = provider_id
        self.__values = dict(values)

    @property
    def provider_id(self) -> str:
        return self.__provider_id

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self.__values))

    def secret(self, name: str) -> SecretValue:
        return self.__values[name]

    def __str__(self) -> str:
        return f"ProviderSecrets(provider_id={self.__provider_id!r}, values=<redacted>)"

    def __repr__(self) -> str:
        return str(self)


def load_provider_secrets(
    config: PublicProviderConfig,
    source: SecretSource,
) -> ProviderSecrets:
    """Resolve every named requirement from the caller-selected source or fail closed."""

    loaded: dict[str, SecretValue] = {}
    for name in config.required_secret_names:
        raw = source.get_secret(name)
        if raw is None or not raw.strip():
            raise MissingSecretError(f"required secret {name!r} is missing or blank")
        loaded[name] = SecretValue(raw)
    return ProviderSecrets(config.provider_id, loaded)
