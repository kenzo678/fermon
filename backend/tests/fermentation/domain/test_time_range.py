from datetime import UTC, datetime, timedelta, timezone, tzinfo

import pytest

from fermon.fermentation.domain import InvalidTimeRangeError, validate_time_range

START = datetime(2026, 1, 1, tzinfo=UTC)


class NoOffset(tzinfo):
    def utcoffset(self, dt: datetime | None) -> timedelta | None:
        return None

    def dst(self, dt: datetime | None) -> timedelta | None:
        return None


def test_accepts_aware_increasing_range() -> None:
    validate_time_range(START, START + timedelta(hours=1))


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (datetime(2026, 1, 1), START + timedelta(hours=1)),
        (START, datetime(2026, 1, 2)),
        (START, datetime(2026, 1, 2, tzinfo=NoOffset())),
        (START, START),
        (START + timedelta(hours=1), START),
        (
            datetime(2026, 1, 1, 12, tzinfo=timezone(timedelta(hours=-3))),
            datetime(2026, 1, 1, 14, tzinfo=UTC),
        ),
    ],
)
def test_rejects_naive_or_non_increasing_range(start: datetime, end: datetime) -> None:
    with pytest.raises(InvalidTimeRangeError):
        validate_time_range(start, end)
