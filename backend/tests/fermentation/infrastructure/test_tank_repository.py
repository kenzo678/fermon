from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from fermon.fermentation.domain import MeasurementType, Reading
from fermon.fermentation.infrastructure.persistence import (
    SqlAlchemyReadingRepository,
    SqlAlchemyTankRepository,
)

pytestmark = pytest.mark.integration

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def make_reading(tank: str, measurement: MeasurementType, value: float, minutes: int) -> Reading:
    return Reading(
        tank, f"{tank}-s", measurement, value, measurement.unit, T0 + timedelta(minutes=minutes)
    )


async def test_ensure_registers_once_and_keeps_the_first_seen_at(
    tank_repository: SqlAlchemyTankRepository, engine: AsyncEngine
) -> None:
    await tank_repository.ensure("tank-1", T0)
    await tank_repository.ensure("tank-1", T0 + timedelta(hours=1))

    tank = await tank_repository.get("tank-1")
    assert tank is not None
    assert (tank.id, tank.display_name, tank.first_seen_at) == ("tank-1", None, T0)
    async with engine.connect() as conn:
        assert await conn.scalar(text("SELECT count(*) FROM tanks")) == 1


async def test_get_unknown_tank_is_none_and_list_is_sorted_by_id(
    tank_repository: SqlAlchemyTankRepository,
) -> None:
    await tank_repository.ensure("tank-2", T0)
    await tank_repository.ensure("tank-1", T0)

    assert await tank_repository.get("nope") is None
    assert [t.id for t in await tank_repository.list()] == ["tank-1", "tank-2"]


async def test_latest_per_measurement_returns_the_newest_reading_of_each_measurement(
    repository: SqlAlchemyReadingRepository,
) -> None:
    for r in [
        make_reading("tank-1", MeasurementType.TEMPERATURE, 18.0, 0),
        make_reading("tank-1", MeasurementType.TEMPERATURE, 19.0, 9),
        make_reading("tank-1", MeasurementType.TEMPERATURE, 17.0, 3),
        make_reading("tank-1", MeasurementType.PRESSURE, 1.0, 4),
        make_reading("tank-2", MeasurementType.ALCOHOL, 5.0, 1),
        make_reading("tank-3", MeasurementType.ALCOHOL, 6.0, 1),  # not requested
    ]:
        await repository.add(r)

    latest = await repository.latest_per_measurement(["tank-1", "tank-2", "tank-empty"])

    assert set(latest) == {"tank-1", "tank-2"}
    assert latest["tank-1"][MeasurementType.TEMPERATURE].value == 19.0
    assert latest["tank-1"][MeasurementType.PRESSURE].value == 1.0
    assert MeasurementType.ALCOHOL not in latest["tank-1"]
    assert latest["tank-2"] == {
        MeasurementType.ALCOHOL: make_reading("tank-2", MeasurementType.ALCOHOL, 5.0, 1)
    }


async def test_latest_per_measurement_without_tank_ids_is_empty(
    repository: SqlAlchemyReadingRepository,
) -> None:
    assert await repository.latest_per_measurement([]) == {}


async def test_ensure_keeps_the_earliest_first_seen_at_for_out_of_order_arrivals(
    tank_repository: SqlAlchemyTankRepository,
) -> None:
    await tank_repository.ensure("tank-1", T0 + timedelta(hours=1))
    await tank_repository.ensure("tank-1", T0)

    tank = await tank_repository.get("tank-1")
    assert tank is not None
    assert tank.first_seen_at == T0


async def test_latest_per_measurement_breaks_timestamp_ties_by_sensor_id(
    repository: SqlAlchemyReadingRepository,
) -> None:
    at = T0 + timedelta(minutes=5)
    for sensor_id, value in [("probe-b", 19.0), ("probe-a", 18.0), ("probe-c", 20.0)]:
        await repository.add(
            Reading("tank-1", sensor_id, MeasurementType.TEMPERATURE, value, "celsius", at)
        )

    for _ in range(3):
        latest = await repository.latest_per_measurement(["tank-1"])
        assert latest["tank-1"][MeasurementType.TEMPERATURE].sensor_id == "probe-c"


async def test_ensure_does_not_rewrite_the_row_when_seen_at_is_not_earlier(
    tank_repository: SqlAlchemyTankRepository, engine: AsyncEngine
) -> None:
    await tank_repository.ensure("tank-1", T0)
    async with engine.connect() as conn:
        before = await conn.scalar(text("SELECT xmin::text FROM tanks WHERE id = 'tank-1'"))

    await tank_repository.ensure("tank-1", T0 + timedelta(minutes=1))

    async with engine.connect() as conn:
        after = await conn.scalar(text("SELECT xmin::text FROM tanks WHERE id = 'tank-1'"))
    assert after == before
