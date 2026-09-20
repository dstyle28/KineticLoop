import pytest

from kineticloop.primitives import (
    CANONICAL_JSON_SCHEME,
    CanonicalizationError,
    canonical_json,
    canonical_json_bytes,
)


def test_canonical_serialization_deterministic_across_key_order_and_unicode_forms() -> None:
    first = {"z": [True, None, 7], "é": "caf\N{LATIN SMALL LETTER E WITH ACUTE}"}
    second = {"e\N{COMBINING ACUTE ACCENT}": "cafe\N{COMBINING ACUTE ACCENT}", "z": [True, None, 7]}

    assert CANONICAL_JSON_SCHEME == "kineticloop-json-v1"
    assert canonical_json(first) == '{"z":[true,null,7],"é":"café"}'
    assert canonical_json_bytes(first) == canonical_json_bytes(second)


@pytest.mark.parametrize(
    "value",
    [1.0, float("nan"), (1, 2), {"value": {1, 2}}, {1: "non-string key"}, 2**63],
)
def test_invalid_input_rejected_for_noncanonical_json_values(value: object) -> None:
    with pytest.raises(CanonicalizationError):
        canonical_json(value)


def test_invalid_input_rejected_for_cycles_and_normalized_key_collisions() -> None:
    cyclic: list[object] = []
    cyclic.append(cyclic)

    with pytest.raises(CanonicalizationError):
        canonical_json(cyclic)
    with pytest.raises(CanonicalizationError):
        canonical_json({"é": 1, "e\N{COMBINING ACUTE ACCENT}": 2})
