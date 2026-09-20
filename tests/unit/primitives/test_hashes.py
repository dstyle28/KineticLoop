import hashlib

import pytest

from kineticloop.primitives import (
    CANONICAL_HASH_SCHEME,
    canonical_json_bytes,
    canonical_sha256,
    sha256_bytes,
    verify_canonical_sha256,
)


class _SubstitutingDigest(str):
    def __str__(self) -> str:
        return "f" * 64


class _BytesSubclass(bytes):
    pass


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


def test_hash_deterministic_returns_exact_builtin_wire_types() -> None:
    digest = canonical_sha256({"value": 1})
    raw_digest = sha256_bytes(b"value")
    verified = verify_canonical_sha256({"value": 1}, digest)

    assert type(digest) is str
    assert type(raw_digest) is str
    assert type(verified) is bool


@pytest.mark.parametrize("expected", ["A" * 64, "0" * 63, "sha256:" + "0" * 64, 123])
def test_invalid_input_rejected_for_noncanonical_hashes(expected: object) -> None:
    with pytest.raises(ValueError):
        verify_canonical_sha256({}, expected)  # type: ignore[arg-type]


def test_invalid_input_rejected_for_nonbyte_raw_hash_input() -> None:
    for value in (bytearray(b"mutable"), _BytesSubclass(b"substituted")):
        with pytest.raises(TypeError, match="hash input must be bytes"):
            sha256_bytes(value)


def test_invalid_input_rejected_for_digest_subclass_with_substituted_identity() -> None:
    payload = {"value": 1}
    stored = canonical_sha256(payload)
    expected = _SubstitutingDigest(stored)

    assert expected == stored
    assert str(expected) != stored
    with pytest.raises(ValueError, match="expected hash must be 64 lower-case hexadecimal characters"):
        verify_canonical_sha256(payload, expected)
