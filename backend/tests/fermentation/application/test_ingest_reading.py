from datetime import UTC, datetime

import pytest

from fermon.fermentation.application import IngestReading, IngestReadingCommand, IngestResult
from fermon.fermentation.domain import InvalidReadingError, MeasurementType, Reading
from tests.fermentation.fakes import InMemoryReadingRepository, InMemoryTankRepository

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def make_command(**overrides: object) -> IngestReadingCommand:
    fields: dict[str, object] = {
        "tank_id": "tank-1",
        "sensor_id": "sensor-1",
        "measurement": "temperature",
        "value": 18.5,
        "unit": "celsius",
        "recorded_at": NOW,
    }
    fields.update(overrides)
    return IngestReadingCommand(**fields)  # type: ignore[arg-type]


async def test_ingest_stores_and_returns_reading() -> None:
    repo = InMemoryReadingRepository()

    result = await IngestReading(repo, InMemoryTankRepository()).execute(make_command())

    expected = Reading("tank-1", "sensor-1", MeasurementType.TEMPERATURE, 18.5, "celsius", NOW)
    assert result == IngestResult(reading=expected, created=True)
    assert repo.readings == [expected]


async def test_duplicate_returns_the_stored_reading_not_the_new_value() -> None:
    repo = InMemoryReadingRepository()
    use_case = IngestReading(repo, InMemoryTankRepository())
    await use_case.execute(make_command(value=18.5))

    result = await use_case.execute(make_command(value=19.0))

    assert result.created is False
    assert result.reading.value == 18.5
    assert [r.value for r in repo.readings] == [18.5]


async def test_unknown_measurement_raises_and_stores_nothing() -> None:
    repo = InMemoryReadingRepository()

    with pytest.raises(InvalidReadingError) as exc:
        await IngestReading(repo, InMemoryTankRepository()).execute(
            make_command(measurement="humidity")
        )

    assert exc.value.field == "measurement"
    assert repo.readings == []


async def test_domain_invalid_value_raises_and_stores_nothing() -> None:
    repo = InMemoryReadingRepository()

    with pytest.raises(InvalidReadingError) as exc:
        await IngestReading(repo, InMemoryTankRepository()).execute(make_command(value=500.0))

    assert exc.value.field == "value"
    assert repo.readings == []


async def test_ingest_registers_the_tank_at_the_first_reading_time() -> None:
    repo, tanks = InMemoryReadingRepository(), InMemoryTankRepository()
    use_case = IngestReading(repo, tanks)

    await use_case.execute(make_command(recorded_at=NOW))
    await use_case.execute(make_command(recorded_at=NOW.replace(hour=13), value=19.0))

    [tank] = await tanks.list()
    assert (tank.id, tank.display_name, tank.first_seen_at) == ("tank-1", None, NOW)


async def test_duplicate_reading_keeps_the_tank_registered_once() -> None:
    repo, tanks = InMemoryReadingRepository(), InMemoryTankRepository()
    use_case = IngestReading(repo, tanks)

    await use_case.execute(make_command())
    await use_case.execute(make_command())

    assert [t.id for t in await tanks.list()] == ["tank-1"]


async def test_invalid_reading_does_not_register_a_tank() -> None:
    repo, tanks = InMemoryReadingRepository(), InMemoryTankRepository()

    with pytest.raises(InvalidReadingError):
        await IngestReading(repo, tanks).execute(make_command(value=500.0))

    assert await tanks.list() == []


async def test_tank_is_registered_before_the_reading_is_stored() -> None:
    order: list[str] = []

    class Spy(InMemoryReadingRepository):
        async def add(self, reading: Reading) -> bool:
            order.append("reading")
            return await super().add(reading)

    class SpyTanks(InMemoryTankRepository):
        async def ensure(self, tank_id: str, seen_at: datetime) -> None:
            order.append("tank")
            await super().ensure(tank_id, seen_at)

    await IngestReading(Spy(), SpyTanks()).execute(make_command())

    assert order == ["tank", "reading"]
