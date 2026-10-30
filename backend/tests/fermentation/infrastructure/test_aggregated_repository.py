from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from fermon.fermentation.domain import AggregationBucket, MeasurementType, Reading
from fermon.fermentation.infrastructure.persistence import SqlAlchemyReadingRepository

pytestmark = pytest.mark.integration

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
TEMP, PRESSURE = MeasurementType.TEMPERATURE, MeasurementType.PRESSURE
ALL = list(MeasurementType)
ONE_MINUTE, ONE_HOUR = AggregationBucket.ONE_MINUTE, AggregationBucket.ONE_HOUR


def reading(
    value: float, seconds: int, m: MeasurementType = TEMP, sensor: str = "s1", tank: str = "tank-1"
) -> Reading:
    return Reading(tank, sensor, m, value, m.unit, T0 + timedelta(seconds=seconds))


async def add_all(repository: SqlAlchemyReadingRepository, readings: list[Reading]) -> None:
    for r in readings:
        await repository.add(r)


async def refresh(engine: AsyncEngine) -> None:
    """Materialize everything now, 1m first (1h is built on top of it)."""
    autocommit = create_async_engine(engine.url, isolation_level="AUTOCOMMIT")
    try:
        async with autocommit.connect() as conn:
            for view in ("readings_1m", "readings_1h"):
                await conn.execute(text(f"CALL refresh_continuous_aggregate('{view}', NULL, NULL)"))
    finally:
        await autocommit.dispose()


async def test_minute_buckets_aggregate_across_sensors_before_any_refresh(
    repository: SqlAlchemyReadingRepository,
) -> None:
    # Nothing was materialized yet (no refresh, and the policy window has not run): the numbers
    # can only come from real-time aggregation over the raw hypertable.
    await add_all(
        repository,
        [
            reading(18.0, 0),
            reading(20.0, 30),
            reading(22.0, 30, sensor="s2"),
            reading(30.0, 61),
            reading(1.0, 10, PRESSURE),
            reading(5.0, 10, tank="tank-2"),
        ],
    )

    points = await repository.aggregated("tank-1", ONE_MINUTE, T0, T0 + timedelta(minutes=5), ALL)

    assert [(p.bucket_start, p.measurement, p.avg, p.min, p.max, p.count) for p in points] == [
        (T0, PRESSURE, 1.0, 1.0, 1.0, 1),  # ties on bucket order by measurement name
        (T0, TEMP, 20.0, 18.0, 22.0, 3),
        (T0 + timedelta(minutes=1), TEMP, 30.0, 30.0, 30.0, 1),
    ]


async def test_materialized_and_real_time_results_agree(
    repository: SqlAlchemyReadingRepository, engine: AsyncEngine
) -> None:
    await add_all(repository, [reading(18.0, 0), reading(20.0, 30), reading(30.0, 61)])
    before = await repository.aggregated("tank-1", ONE_MINUTE, T0, T0 + timedelta(hours=1), ALL)

    await refresh(engine)

    after = await repository.aggregated("tank-1", ONE_MINUTE, T0, T0 + timedelta(hours=1), ALL)
    assert after == before
    assert [p.count for p in after] == [2, 1]


async def test_readings_newer_than_the_last_refresh_show_up_without_refreshing_again(
    repository: SqlAlchemyReadingRepository, engine: AsyncEngine
) -> None:
    await add_all(repository, [reading(18.0, 0)])
    await refresh(engine)

    await add_all(repository, [reading(20.0, 300)])

    points = await repository.aggregated("tank-1", ONE_MINUTE, T0, T0 + timedelta(minutes=10), ALL)
    assert [(p.bucket_start, p.avg) for p in points] == [
        (T0, 18.0),
        (T0 + timedelta(minutes=5), 20.0),
    ]


async def test_late_reading_in_an_already_materialized_bucket_waits_for_the_next_refresh(
    repository: SqlAlchemyReadingRepository, engine: AsyncEngine
) -> None:
    # Characterization of TimescaleDB behavior, not a requirement: real-time aggregation only
    # covers data NEWER than the materialization watermark. A reading that lands in a bucket that
    # was already materialized is invisible until the refresh policy (or a manual refresh) runs.
    await add_all(repository, [reading(18.0, 0)])
    await refresh(engine)
    await add_all(repository, [reading(20.0, 10)])

    [stale] = await repository.aggregated("tank-1", ONE_MINUTE, T0, T0 + timedelta(minutes=1), ALL)
    await refresh(engine)
    [fresh] = await repository.aggregated("tank-1", ONE_MINUTE, T0, T0 + timedelta(minutes=1), ALL)

    assert (stale.avg, stale.count) == (18.0, 1)
    assert (fresh.avg, fresh.count) == (19.0, 2)


async def test_hour_bucket_is_a_weighted_average_of_the_minute_buckets(
    repository: SqlAlchemyReadingRepository, engine: AsyncEngine
) -> None:
    # Minute 0 holds one reading (10), minute 1 holds three (20): the hourly average is the
    # weighted 17.5, not the mean of the minute averages (15).
    await add_all(
        repository,
        [reading(10.0, 0), reading(20.0, 60), reading(20.0, 70), reading(20.0, 80)],
    )
    await refresh(engine)

    [point] = await repository.aggregated("tank-1", ONE_HOUR, T0, T0 + timedelta(hours=1), [TEMP])

    assert (point.bucket_start, point.avg, point.min, point.max, point.count) == (
        T0,
        17.5,
        10.0,
        20.0,
        4,
    )


async def test_hour_bucket_without_refresh_uses_real_time_aggregation(
    repository: SqlAlchemyReadingRepository,
) -> None:
    await add_all(
        repository,
        [reading(10.0, 0), reading(20.0, 60), reading(20.0, 3600 + 5)],
    )

    points = await repository.aggregated("tank-1", ONE_HOUR, T0, T0 + timedelta(hours=3), [TEMP])

    assert [(p.bucket_start, p.avg, p.count) for p in points] == [
        (T0, 15.0, 2),
        (T0 + timedelta(hours=1), 20.0, 1),
    ]


async def test_range_is_half_open_and_measurements_are_filtered(
    repository: SqlAlchemyReadingRepository,
) -> None:
    await add_all(
        repository,
        [reading(1.0, 0), reading(2.0, 60), reading(3.0, 120), reading(9.0, 60, PRESSURE)],
    )

    points = await repository.aggregated(
        "tank-1", ONE_MINUTE, T0 + timedelta(minutes=1), T0 + timedelta(minutes=2), [TEMP]
    )

    assert [(p.bucket_start, p.avg) for p in points] == [(T0 + timedelta(minutes=1), 2.0)]


async def test_empty_measurement_selection_returns_nothing(
    repository: SqlAlchemyReadingRepository,
) -> None:
    await add_all(repository, [reading(1.0, 0)])

    assert await repository.aggregated("tank-1", ONE_MINUTE, T0, T0 + timedelta(hours=1), []) == []
