import hashlib

import pytest

from kineticloop.primitives import (
    CANONICAL_HASH_SCHEME,
    canonical_json_bytes,
    canonical_sha256,
    sha256_bytes,
    verify_canonical_sha256,
)


def test_hash_deterministic_and_bound_to_the_versioned_canonical_payload() -> None:
    first = {"subject_id": "8c7d83ee-49db-4b2c-9df2-0b0f158c328f", "revision": 2}
    reordered = {"revision": 2, "subject_id": "8c7d83ee-49db-4b2c-9df2-0b0f158c328f"}
    expected = hashlib.sha256(canonical_json_bytes(first)).hexdigest()

    assert CANONICAL_HASH_SCHEME == "sha256-kineticloop-json-v1"
    assert canonical_sha256(first) == expected
    assert canonical_sha256(reordered) == expected
    assert verify_canonical_sha256(first, expected)
    assert not verify_canonical_sha256({**first, "revision": 3}, expected)
    assert sha256_bytes(b"") == hashlib.sha256(b"").hexdigest()


@pytest.mark.parametrize("expected", ["A" * 64, "0" * 63, "sha256:" + "0" * 64, 123])
def test_invalid_input_rejected_for_noncanonical_hashes(expected: object) -> None:
    with pytest.raises(ValueError):
        verify_canonical_sha256({}, expected)  # type: ignore[arg-type]


def test_invalid_input_rejected_for_nonbyte_raw_hash_input() -> None:
    with pytest.raises(TypeError):
        sha256_bytes(bytearray(b"mutable"))
