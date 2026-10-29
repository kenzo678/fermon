from datetime import UTC, datetime, timedelta

import pytest

from fermon.fermentation.application import ListReadings
from fermon.fermentation.domain import InvalidTimeRangeError, MeasurementType, Reading
from tests.fermentation.fakes import InMemoryReadingRepository

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def reading(tank_id: str, offset_min: int) -> Reading:
    return Reading(
        tank_id,
        "sensor-1",
        MeasurementType.TEMPERATURE,
        18.0,
        "celsius",
        T0 + timedelta(minutes=offset_min),
    )


async def test_returns_tank_readings_in_range_sorted_end_exclusive() -> None:
    repo = InMemoryReadingRepository()
    for r in [
        reading("tank-1", 20),
        reading("tank-1", 0),
        reading("tank-1", 10),
        reading("tank-1", 30),  # == end, excluded
        reading("tank-1", -1),  # before start
        reading("tank-2", 5),  # other tank
    ]:
        await repo.add(r)

    result = await ListReadings(repo).execute("tank-1", T0, T0 + timedelta(minutes=30))

    assert [r.recorded_at for r in result] == [
        T0,
        T0 + timedelta(minutes=10),
        T0 + timedelta(minutes=20),
    ]


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (T0, T0),
        (T0 + timedelta(minutes=1), T0),
        (T0.replace(tzinfo=None), T0 + timedelta(minutes=1)),
        (T0, (T0 + timedelta(minutes=1)).replace(tzinfo=None)),
    ],
)
async def test_invalid_range_raises(start: datetime, end: datetime) -> None:
    with pytest.raises(InvalidTimeRangeError):
        await ListReadings(InMemoryReadingRepository()).execute("tank-1", start, end)
