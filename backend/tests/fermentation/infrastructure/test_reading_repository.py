from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from fermon.fermentation.domain import InvalidTimeRangeError, MeasurementType, Reading
from fermon.fermentation.infrastructure.persistence import SqlAlchemyReadingRepository
from tests.fermentation.fakes import InMemoryReadingRepository

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


STREAK_T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


async def _store(repository: SqlAlchemyReadingRepository, points: list[tuple[int, float]]) -> None:
    for minute, value in points:
        await repository.add(
            Reading(
                "tank-1",
                "s1",
                MeasurementType.TEMPERATURE,
                value,
                "celsius",
                STREAK_T0 + timedelta(minutes=minute),
            )
        )


def _at(minute: int) -> datetime:
    return STREAK_T0 + timedelta(minutes=minute)


async def _streak(
    repository: SqlAlchemyReadingRepository, *, in_range: bool, since: int = -60, until: int = 60
) -> datetime | None:
    return await repository.streak_start(
        "tank-1", MeasurementType.TEMPERATURE, 18.0, 21.0, in_range, _at(since), _at(until)
    )


async def test_streak_start_is_the_first_reading_after_the_last_one_of_the_other_class(
    repository: SqlAlchemyReadingRepository,
) -> None:
    # 0 in, 1 in, 2 OUT, 3 OUT, 4 in, 5 OUT, 6 OUT, 7 OUT
    await _store(
        repository,
        [(0, 20.0), (1, 20.0), (2, 25.0), (3, 25.0), (4, 20.0), (5, 25.0), (6, 22.0), (7, 15.0)],
    )

    assert await _streak(repository, in_range=False) == _at(5)
    assert await _streak(repository, in_range=True) is None  # the newest reading is out of range
    assert await _streak(repository, in_range=True, until=4) == _at(4)
    assert await _streak(repository, in_range=True, until=1) == _at(0)
    assert await _streak(repository, in_range=False, until=3) == _at(2)


async def test_streak_start_limits_are_inclusive_and_the_window_bounds_the_search(
    repository: SqlAlchemyReadingRepository,
) -> None:
    await _store(repository, [(0, 25.0), (1, 18.0), (2, 21.0), (3, 25.0), (4, 25.0)])

    assert await _streak(repository, in_range=True, until=2) == _at(1)  # 18.0 and 21.0 are in
    assert await _streak(repository, in_range=False) == _at(3)
    # A window starting later cannot see the earlier readings.
    assert await _streak(repository, in_range=False, since=4) == _at(4)
    assert await _streak(repository, in_range=False, since=5) is None


async def test_streak_start_supports_one_sided_ranges_and_ignores_other_series(
    repository: SqlAlchemyReadingRepository,
) -> None:
    await _store(repository, [(0, 20.0)])
    await repository.add(
        Reading("tank-1", "s2", MeasurementType.PRESSURE, 5.0, "bar", _at(1))
    )  # other measurement
    await repository.add(
        Reading("tank-2", "s1", MeasurementType.TEMPERATURE, 99.0, "celsius", _at(2))
    )  # other tank

    only_max = await repository.streak_start(
        "tank-1", MeasurementType.PRESSURE, None, 1.0, False, _at(-1), _at(10)
    )
    assert only_max == _at(1)
    assert await _streak(repository, in_range=True) == _at(0)


async def test_streak_start_is_exact_beyond_any_window_when_since_is_the_batch_start(
    repository: SqlAlchemyReadingRepository,
) -> None:
    # Hours apart: the streak start must not depend on how far back the caller looks.
    await _store(repository, [(0, 25.0), (600, 20.0), (1200, 20.0), (1800, 25.0), (2400, 25.0)])

    assert await _streak(repository, in_range=False, since=-60, until=2400) == _at(1800)
    assert await _streak(repository, in_range=True, since=-60, until=1200) == _at(600)


async def test_streak_start_with_a_mixed_newest_instant_is_none_whatever_the_insertion_order(
    repository: SqlAlchemyReadingRepository,
) -> None:
    for sensor, value in (("s1", 25.0), ("s2", 20.0)):
        await repository.add(
            Reading("tank-1", sensor, MeasurementType.TEMPERATURE, value, "celsius", _at(3))
        )

    assert await _streak(repository, in_range=True) is None
    assert await _streak(repository, in_range=False) is None


@pytest.mark.parametrize("out_first", [True, False])
async def test_fake_and_sql_streak_start_agree_when_one_instant_mixes_classes(
    repository: SqlAlchemyReadingRepository, out_first: bool
) -> None:
    fake = InMemoryReadingRepository()
    tie = [("s1", 25.0), ("s2", 20.0)]
    tie = tie if out_first else tie[::-1]
    points = [
        (0, "s1", 20.0),
        (1, tie[0][0], tie[0][1]),
        (1, tie[1][0], tie[1][1]),
        (2, "s1", 20.0),
    ]
    for minute, sensor, value in points:
        reading = Reading(
            "tank-1", sensor, MeasurementType.TEMPERATURE, value, "celsius", _at(minute)
        )
        await repository.add(reading)
        await fake.add(reading)

    for until in (1, 2):
        for in_range in (True, False):
            args = (
                "tank-1",
                MeasurementType.TEMPERATURE,
                18.0,
                21.0,
                in_range,
                _at(-60),
                _at(until),
            )
            assert await fake.streak_start(*args) == await repository.streak_start(*args)
    # Characterization of the shared semantics: a tie at the newest instant has no streak, and a
    # mixed instant in the past ends the other class's streak but does not start this one.
    assert await _streak(repository, in_range=True, until=1) is None
    assert await _streak(repository, in_range=True, until=2) == _at(2)
