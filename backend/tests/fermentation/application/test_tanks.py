from datetime import UTC, datetime, timedelta

import pytest

from fermon.fermentation.application import GetTank, ListTanks, TankOverview
from fermon.fermentation.domain import (
    InvalidIdentifierError,
    MeasurementType,
    Reading,
    TankNotFoundError,
)
from tests.fermentation.fakes import InMemoryReadingRepository, InMemoryTankRepository

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def reading(tank: str, measurement: MeasurementType, value: float, minutes: int) -> Reading:
    at = T0 + timedelta(minutes=minutes)
    return Reading(tank, f"{tank}-s", measurement, value, measurement.unit, at)


async def seeded() -> tuple[InMemoryReadingRepository, InMemoryTankRepository]:
    readings, tanks = InMemoryReadingRepository(), InMemoryTankRepository()
    for tank_id in ("tank-2", "tank-1", "tank-3"):
        await tanks.ensure(tank_id, T0)
    for r in (
        reading("tank-1", MeasurementType.TEMPERATURE, 18.0, 0),
        reading("tank-1", MeasurementType.TEMPERATURE, 19.0, 5),  # latest temperature
        reading("tank-1", MeasurementType.PRESSURE, 1.0, 2),
        reading("tank-2", MeasurementType.ALCOHOL, 4.0, 1),
    ):
        await readings.add(r)
    return readings, tanks


async def test_list_tanks_returns_tanks_sorted_by_id_with_latest_reading_per_measurement() -> None:
    readings, tanks = await seeded()

    overview = await ListTanks(tanks, readings).execute()

    assert [o.tank.id for o in overview] == ["tank-1", "tank-2", "tank-3"]
    first, second, third = overview
    assert first.latest == {
        MeasurementType.TEMPERATURE: reading("tank-1", MeasurementType.TEMPERATURE, 19.0, 5),
        MeasurementType.PRESSURE: reading("tank-1", MeasurementType.PRESSURE, 1.0, 2),
    }
    assert list(second.latest) == [MeasurementType.ALCOHOL]
    assert third.latest == {}


async def test_list_tanks_is_empty_without_tanks() -> None:
    result = await ListTanks(InMemoryTankRepository(), InMemoryReadingRepository()).execute()

    assert result == []


async def test_get_tank_returns_the_tank_with_its_latest_readings() -> None:
    readings, tanks = await seeded()

    result = await GetTank(tanks, readings).execute(" tank-1 ")

    assert isinstance(result, TankOverview)
    assert result.tank.id == "tank-1"
    assert result.latest[MeasurementType.TEMPERATURE].value == 19.0


async def test_get_unknown_tank_raises_not_found() -> None:
    readings, tanks = await seeded()

    with pytest.raises(TankNotFoundError) as exc:
        await GetTank(tanks, readings).execute("nope")

    assert exc.value.tank_id == "nope"


async def test_get_blank_tank_id_raises_invalid_identifier() -> None:
    readings, tanks = await seeded()

    with pytest.raises(InvalidIdentifierError):
        await GetTank(tanks, readings).execute("  ")


async def test_fake_ensure_keeps_the_earliest_first_seen_at() -> None:
    tanks = InMemoryTankRepository()
    later = datetime(2026, 1, 1, 13, 0, tzinfo=UTC)
    earlier = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    await tanks.ensure("tank-1", later)
    await tanks.ensure("tank-1", earlier)

    tank = await tanks.get("tank-1")
    assert tank is not None
    assert tank.first_seen_at == earlier


async def test_fake_latest_breaks_timestamp_ties_by_sensor_id_like_sql() -> None:
    readings = InMemoryReadingRepository()
    at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    for sensor_id, value in [("probe-c", 20.0), ("probe-a", 18.0), ("probe-b", 19.0)]:
        await readings.add(
            Reading("tank-1", sensor_id, MeasurementType.TEMPERATURE, value, "celsius", at)
        )

    latest = await readings.latest_per_measurement(["tank-1"])

    assert latest["tank-1"][MeasurementType.TEMPERATURE].sensor_id == "probe-c"
