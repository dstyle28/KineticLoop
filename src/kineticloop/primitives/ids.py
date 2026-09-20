"""Canonical identifiers.

The wire form is a lower-case, hyphenated RFC 4122 UUID. New identifiers use
UUIDv4. Identifier ordering has no domain meaning.
"""

import re
from uuid import RFC_4122, UUID, uuid4

_CANONICAL_UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def canonical_id(value: str | UUID) -> str:
    """Return *value* in canonical UUID wire form or reject it.

    Strings must already be canonical. This deliberately rejects convenient
    UUID spellings such as upper-case, braces, URNs, and unhyphenated hex so
    distinct input representations cannot enter durable keys.
    """

    if type(value) is UUID:
        text = str(value)
    elif isinstance(value, str):
        text = value
    else:
        raise TypeError("identifier must be a string or UUID")

    if _CANONICAL_UUID.fullmatch(text) is None:
        raise ValueError("identifier must be a lower-case, hyphenated RFC 4122 UUID")
    try:
        parsed = UUID(text)
    except ValueError as error:
        raise ValueError("identifier is not a valid UUID") from error

    if parsed.variant != RFC_4122:
        raise ValueError("identifier must use the RFC 4122 variant")
    return text


def new_id() -> str:
    """Create a new canonical UUIDv4 identifier."""

    return canonical_id(uuid4())


def is_canonical_id(value: object) -> bool:
    """Return whether *value* is a canonical identifier string."""

    if not isinstance(value, str):
        return False
    try:
        canonical_id(value)
    except (TypeError, ValueError):
        return False
    return True
