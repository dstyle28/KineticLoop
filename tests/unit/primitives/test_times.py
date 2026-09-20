from datetime import UTC, datetime, timedelta, timezone, tzinfo
from typing import Any

import pytest

from kineticloop.primitives import canonical_utc, normalize_utc, parse_utc, utc_now


class _SubstitutingTimeString(str):
    def endswith(self, suffix: Any, start: Any = 0, end: Any = None) -> bool:
        return True

    def __getitem__(self, key: object) -> str:
        return "2030-12-31T23:59:59"


class _SubstitutingDatetime(datetime):
    def utcoffset(self) -> timedelta:
        return timedelta(0)

    def astimezone(self, tz: tzinfo | None = None) -> "_SubstitutingDatetime":
        return _SubstitutingDatetime(2030, 12, 31, 23, 59, 59, tzinfo=UTC)

    def isoformat(self, sep: str = "T", timespec: str = "auto") -> str:
        return "arbitrary output"


def test_utc_time_normalized_from_offset_and_rfc3339_inputs() -> None:
    source = datetime(2026, 3, 8, 1, 30, 45, 123456, tzinfo=timezone(timedelta(hours=-8)))

    assert normalize_utc(source) == datetime(2026, 3, 8, 9, 30, 45, 123456, tzinfo=UTC)
    assert canonical_utc(source) == "2026-03-08T09:30:45.123456Z"
    assert parse_utc("2026-03-08T01:30:45.123456-08:00") == normalize_utc(source)
    assert utc_now().tzinfo is UTC


@pytest.mark.parametrize(
    "value",
    [
        datetime(2026, 1, 1),
        "2026-01-01T00:00:00",
        "2026-01-01 00:00:00Z",
        "2026-02-30T00:00:00Z",
    ],
)
def test_invalid_input_rejected_for_untrusted_times(value: datetime | str) -> None:
    with pytest.raises((TypeError, ValueError)):
        canonical_utc(value)


def test_invalid_input_rejected_for_string_subclass_with_method_substitution() -> None:
    value = _SubstitutingTimeString("2026-01-01T00:00:00Z")

    with pytest.raises(TypeError, match="instant must be an RFC 3339 string"):
        parse_utc(value)
    with pytest.raises(TypeError, match="instant must be a datetime or RFC 3339 string"):
        canonical_utc(value)


def test_invalid_input_rejected_for_datetime_subclass_with_method_substitution() -> None:
    value = _SubstitutingDatetime(2026, 1, 1, tzinfo=UTC)

    with pytest.raises(TypeError, match="instant must be a datetime"):
        normalize_utc(value)
    with pytest.raises(TypeError, match="instant must be a datetime"):
        canonical_utc(value)


def test_utc_time_normalized_returns_exact_builtin_wire_types() -> None:
    instant = normalize_utc(datetime(2026, 1, 1, tzinfo=UTC))
    text = canonical_utc(instant)

    assert type(instant) is datetime
    assert type(text) is str
