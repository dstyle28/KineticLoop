from datetime import UTC, datetime, timedelta, timezone

import pytest

from kineticloop.primitives import canonical_utc, normalize_utc, parse_utc, utc_now


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
