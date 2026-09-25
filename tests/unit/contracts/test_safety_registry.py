from __future__ import annotations

import pytest

from kineticloop.contracts.safety_registry import (
    RegistryDenialCode,
    RegistryDenied,
    RegistryGateTimeoutError,
    RegistryUnavailableError,
    command_requires_registry,
    fail_closed_registry_check,
)


def test_registry_unavailable_or_timeout_denies() -> None:
    def unavailable() -> None:
        raise RegistryUnavailableError

    def timeout() -> None:
        raise RegistryGateTimeoutError

    with pytest.raises(RegistryDenied) as unavailable_denial:
        fail_closed_registry_check(unavailable)
    assert unavailable_denial.value.code is RegistryDenialCode.REGISTRY_UNAVAILABLE

    with pytest.raises(RegistryDenied) as timeout_denial:
        fail_closed_registry_check(timeout)
    assert timeout_denial.value.code is RegistryDenialCode.REGISTRY_TIMEOUT


def test_stop_has_no_registry_dependency() -> None:
    assert not command_requires_registry("STOP")
    assert not command_requires_registry("FORCE_REST")
    assert command_requires_registry("PublishManifest")
    assert command_requires_registry("ContinueSession")
