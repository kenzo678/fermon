from datetime import UTC, datetime, timedelta

import pytest

from fermon.fermentation.application import ListAggregatedReadings
from fermon.fermentation.domain import (
    AggregationBucket,
    InvalidIdentifierError,
    InvalidTimeRangeError,
    MeasurementType,
    Reading,
    TankNotFoundError,
    TooManyPointsError,
)
from tests.fermentation.fakes import InMemoryReadingRepository, InMemoryTankRepository

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
TEMP, PRESSURE = MeasurementType.TEMPERATURE, MeasurementType.PRESSURE


def reading(m: MeasurementType, value: float, seconds: int, sensor: str = "s1") -> Reading:
    return Reading("tank-1", sensor, m, value, m.unit, T0 + timedelta(seconds=seconds))


async def seeded() -> ListAggregatedReadings:
    readings, tanks = InMemoryReadingRepository(), InMemoryTankRepository()
    await tanks.ensure("tank-1", T0)
    for r in (
        reading(TEMP, 18.0, 0),
        reading(TEMP, 20.0, 30),
        reading(TEMP, 22.0, 30, sensor="s2"),  # same measurement, other sensor: same bucket
        reading(TEMP, 30.0, 61),
        reading(PRESSURE, 1.0, 10),
        reading(TEMP, 99.0, 3600),  # next hour
    ):
        await readings.add(r)
    return ListAggregatedReadings(tanks, readings)


async def test_minute_buckets_aggregate_across_sensors_ascending() -> None:
    use_case = await seeded()

    points = await use_case.execute(
        "tank-1", AggregationBucket.ONE_MINUTE, T0, T0 + timedelta(minutes=5), [TEMP]
    )

    assert [(p.bucket_start, p.avg, p.min, p.max, p.count) for p in points] == [
        (T0, 20.0, 18.0, 22.0, 3),
        (T0 + timedelta(minutes=1), 30.0, 30.0, 30.0, 1),
    ]
    assert {p.measurement for p in points} == {TEMP}


async def test_hour_bucket_combines_the_whole_hour() -> None:
    use_case = await seeded()

    points = await use_case.execute(
        "tank-1", AggregationBucket.ONE_HOUR, T0, T0 + timedelta(hours=2), [TEMP]
    )

    assert [(p.bucket_start, p.count) for p in points] == [
        (T0, 4),
        (T0 + timedelta(hours=1), 1),
    ]
    assert points[0].avg == pytest.approx((18 + 20 + 22 + 30) / 4)


async def test_without_filter_every_measurement_is_returned() -> None:
    use_case = await seeded()

    points = await use_case.execute(
        "tank-1", AggregationBucket.ONE_MINUTE, T0, T0 + timedelta(minutes=5)
    )

    assert {p.measurement for p in points} == {TEMP, PRESSURE}


async def test_range_is_half_open_on_bucket_start() -> None:
    use_case = await seeded()

    points = await use_case.execute(
        "tank-1", AggregationBucket.ONE_MINUTE, T0, T0 + timedelta(minutes=1), [TEMP]
    )

    assert [p.bucket_start for p in points] == [T0]


async def test_unknown_tank_raises_not_found() -> None:
    use_case = await seeded()

    with pytest.raises(TankNotFoundError):
        await use_case.execute("nope", AggregationBucket.ONE_MINUTE, T0, T0 + timedelta(hours=1))


async def test_blank_tank_id_is_invalid() -> None:
    use_case = await seeded()

    with pytest.raises(InvalidIdentifierError):
        await use_case.execute(" ", AggregationBucket.ONE_MINUTE, T0, T0 + timedelta(hours=1))


async def test_invalid_range_is_rejected_before_the_tank_lookup() -> None:
    use_case = await seeded()

    with pytest.raises(InvalidTimeRangeError):
        await use_case.execute("nope", AggregationBucket.ONE_MINUTE, T0, T0)


async def test_too_many_points_is_rejected() -> None:
    use_case = await seeded()

    with pytest.raises(TooManyPointsError):
        await use_case.execute("tank-1", AggregationBucket.ONE_MINUTE, T0, T0 + timedelta(days=30))
