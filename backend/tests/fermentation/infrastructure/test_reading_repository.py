from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from fermon.fermentation.domain import InvalidTimeRangeError, MeasurementType, Reading
from fermon.fermentation.infrastructure.persistence import SqlAlchemyReadingRepository

pytestmark = pytest.mark.integration

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def make_reading(
    *,
    tank_id: str = "tank-1",
    sensor_id: str = "s1",
    measurement: MeasurementType = MeasurementType.TEMPERATURE,
    value: float = 18.5,
    unit: str = "celsius",
    recorded_at: datetime = T0,
) -> Reading:
    return Reading(tank_id, sensor_id, measurement, value, unit, recorded_at)


async def test_add_then_list_round_trips_all_fields(
    repository: SqlAlchemyReadingRepository,
) -> None:
    reading = make_reading(
        measurement=MeasurementType.PRESSURE,
        value=1.25,
        unit="bar",
        recorded_at=datetime(2026, 1, 1, 9, 0, tzinfo=timezone(timedelta(hours=-3))),
    )
    await repository.add(reading)

    [stored] = await repository.list_by_tank(
        "tank-1", T0 - timedelta(days=1), T0 + timedelta(days=1)
    )

    assert stored == reading
    assert stored.recorded_at.utcoffset() is not None
    assert stored.recorded_at == reading.recorded_at


async def test_range_is_half_open_and_ordered_ascending(
    repository: SqlAlchemyReadingRepository,
) -> None:
    times = [T0 + timedelta(minutes=m) for m in (2, 0, 1, 3)]
    for moment in times:
        await repository.add(make_reading(recorded_at=moment))

    result = await repository.list_by_tank("tank-1", T0, T0 + timedelta(minutes=3))

    assert [r.recorded_at for r in result] == [T0 + timedelta(minutes=m) for m in (0, 1, 2)]


async def test_other_tanks_are_excluded(repository: SqlAlchemyReadingRepository) -> None:
    await repository.add(make_reading(tank_id="tank-1"))
    await repository.add(make_reading(tank_id="tank-2"))

    result = await repository.list_by_tank("tank-2", T0, T0 + timedelta(hours=1))

    assert [r.tank_id for r in result] == ["tank-2"]


async def test_duplicate_add_is_a_no_op(
    repository: SqlAlchemyReadingRepository, engine: AsyncEngine
) -> None:
    await repository.add(make_reading())
    await repository.add(make_reading(value=19.0))

    async with engine.connect() as conn:
        count = await conn.scalar(text("SELECT count(*) FROM readings"))
    assert count == 1
    async with engine.connect() as conn:
        stored_value = await conn.scalar(text("SELECT value FROM readings"))
    assert stored_value == 18.5


async def test_add_reports_whether_it_inserted(
    repository: SqlAlchemyReadingRepository,
) -> None:
    assert await repository.add(make_reading()) is True
    assert await repository.add(make_reading(value=19.0)) is False
    assert await repository.add(make_reading(sensor_id="s2")) is True


async def test_get_returns_the_stored_reading_or_none(
    repository: SqlAlchemyReadingRepository,
) -> None:
    stored = make_reading()
    await repository.add(stored)
    other_offset = T0.astimezone(timezone(timedelta(hours=2)))

    found = await repository.get("tank-1", "s1", MeasurementType.TEMPERATURE, other_offset)
    missing = await repository.get("tank-1", "s1", MeasurementType.PRESSURE, T0)

    assert found == stored
    assert missing is None


async def test_readings_table_is_a_hypertable(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        name = await conn.scalar(
            text(
                "SELECT hypertable_name FROM timescaledb_information.hypertables "
                "WHERE hypertable_name = 'readings'"
            )
        )
    assert name == "readings"


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (datetime(2026, 1, 1), T0),
        (T0, datetime(2026, 1, 2)),
        (T0, T0),
        (T0 + timedelta(hours=1), T0),
    ],
)
async def test_list_by_tank_rejects_naive_or_inverted_range(
    repository: SqlAlchemyReadingRepository, start: datetime, end: datetime
) -> None:
    with pytest.raises(InvalidTimeRangeError):
        await repository.list_by_tank("tank-1", start, end)
