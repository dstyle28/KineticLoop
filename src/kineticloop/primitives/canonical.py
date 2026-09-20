"""Versioned deterministic serialization for hash-bound JSON payloads.

Version 1 accepts only JSON objects composed of strings, booleans, null,
signed 64-bit integers, arrays, and objects with string keys. Floating-point
numbers are excluded because their textual and non-finite forms are unsafe for
cross-runtime hash bindings. Strings and object keys are normalized to NFC.
"""

import json
import unicodedata
from typing import TypeAlias

CANONICAL_JSON_SCHEME = "kineticloop-json-v1"

JsonScalar: TypeAlias = None | bool | int | str
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]

_MIN_SIGNED_64 = -(2**63)
_MAX_SIGNED_64 = 2**63 - 1


class CanonicalizationError(ValueError):
    """Raised when a value has no representation in the canonical scheme."""


def _normalized_string(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value)
    try:
        normalized.encode("utf-8")
    except UnicodeEncodeError as error:
        raise CanonicalizationError("strings must contain valid Unicode scalar values") from error
    return normalized


def _utf16_sort_key(value: str) -> bytes:
    return value.encode("utf-16-be")


def _normalize(value: object, active: set[int]) -> JsonValue:
    if value is None or type(value) is bool:
        return value
    if type(value) is int:
        if not _MIN_SIGNED_64 <= value <= _MAX_SIGNED_64:
            raise CanonicalizationError("integers must fit in a signed 64-bit value")
        return value
    if type(value) is str:
        return _normalized_string(value)

    if type(value) is dict:
        marker = id(value)
        if marker in active:
            raise CanonicalizationError("cyclic values cannot be serialized")
        active.add(marker)
        try:
            entries: list[tuple[str, JsonValue]] = []
            seen_keys: set[str] = set()
            for key, member in value.items():
                if type(key) is not str:
                    raise CanonicalizationError("object keys must be strings")
                normalized_key = _normalized_string(key)
                if normalized_key in seen_keys:
                    raise CanonicalizationError("object keys must remain unique after NFC normalization")
                seen_keys.add(normalized_key)
                entries.append((normalized_key, _normalize(member, active)))
            entries.sort(key=lambda item: _utf16_sort_key(item[0]))
            return dict(entries)
        finally:
            active.remove(marker)

    if type(value) is list:
        marker = id(value)
        if marker in active:
            raise CanonicalizationError("cyclic values cannot be serialized")
        active.add(marker)
        try:
            return [_normalize(member, active) for member in value]
        finally:
            active.remove(marker)

    raise CanonicalizationError(f"unsupported canonical JSON value: {type(value).__name__}")


def canonical_json(value: object) -> str:
    """Serialize *value* using the deterministic version 1 JSON scheme."""

    normalized = _normalize(value, set())
    return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def canonical_json_bytes(value: object) -> bytes:
    """Serialize *value* to canonical UTF-8 bytes."""

    return canonical_json(value).encode("utf-8")
