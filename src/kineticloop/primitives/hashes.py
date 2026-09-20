"""Deterministic SHA-256 helpers for bytes and canonical JSON payloads."""

import hashlib
import hmac
import re

from kineticloop.primitives.canonical import canonical_json_bytes

CANONICAL_HASH_SCHEME = "sha256-kineticloop-json-v1"

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


def sha256_bytes(value: bytes) -> str:
    """Return the lower-case SHA-256 hex digest for immutable bytes."""

    if type(value) is not bytes:
        raise TypeError("hash input must be bytes")
    return hashlib.sha256(value).hexdigest()


def canonical_sha256(value: object) -> str:
    """Hash a value after canonical JSON version 1 serialization."""

    return sha256_bytes(canonical_json_bytes(value))


def verify_canonical_sha256(value: object, expected: str) -> bool:
    """Compare a canonical payload hash against a canonical digest."""

    if not isinstance(expected, str) or _SHA256_HEX.fullmatch(expected) is None:
        raise ValueError("expected hash must be 64 lower-case hexadecimal characters")
    return hmac.compare_digest(canonical_sha256(value), expected)
