"""UTC instant normalization and canonical RFC 3339 formatting."""

import re
from datetime import UTC, datetime

_RFC3339_INSTANT = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$"
)


def normalize_utc(value: datetime) -> datetime:
    """Normalize a timezone-aware datetime to a UTC instant."""

    if not isinstance(value, datetime):
        raise TypeError("instant must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("instant must include a UTC offset")
    return value.astimezone(UTC)


def parse_utc(value: str) -> datetime:
    """Parse an RFC 3339 instant and normalize it to UTC."""

    if not isinstance(value, str):
        raise TypeError("instant must be an RFC 3339 string")
    if _RFC3339_INSTANT.fullmatch(value) is None:
        raise ValueError("instant must be RFC 3339 with an explicit UTC offset")

    source = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(source)
    except ValueError as error:
        raise ValueError("instant is not a valid RFC 3339 timestamp") from error
    return normalize_utc(parsed)


def canonical_utc(value: datetime | str) -> str:
    """Return an instant as a UTC RFC 3339 string with microsecond precision."""

    instant = parse_utc(value) if isinstance(value, str) else normalize_utc(value)
    return instant.isoformat(timespec="microseconds").replace("+00:00", "Z")


def utc_now() -> datetime:
    """Read the system clock as a timezone-aware UTC instant."""

    return datetime.now(UTC)
