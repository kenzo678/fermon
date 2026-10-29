from datetime import UTC, datetime

import pytest

from fermon.fermentation.application import IngestReading, IngestReadingCommand, IngestResult
from fermon.fermentation.domain import InvalidReadingError, MeasurementType, Reading
from tests.fermentation.fakes import InMemoryReadingRepository

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

    result = await IngestReading(repo).execute(make_command())

    expected = Reading("tank-1", "sensor-1", MeasurementType.TEMPERATURE, 18.5, "celsius", NOW)
    assert result == IngestResult(reading=expected, created=True)
    assert repo.readings == [expected]


async def test_duplicate_returns_the_stored_reading_not_the_new_value() -> None:
    repo = InMemoryReadingRepository()
    use_case = IngestReading(repo)
    await use_case.execute(make_command(value=18.5))

    result = await use_case.execute(make_command(value=19.0))

    assert result.created is False
    assert result.reading.value == 18.5
    assert [r.value for r in repo.readings] == [18.5]


async def test_unknown_measurement_raises_and_stores_nothing() -> None:
    repo = InMemoryReadingRepository()

    with pytest.raises(InvalidReadingError) as exc:
        await IngestReading(repo).execute(make_command(measurement="humidity"))

    assert exc.value.field == "measurement"
    assert repo.readings == []


async def test_domain_invalid_value_raises_and_stores_nothing() -> None:
    repo = InMemoryReadingRepository()

    with pytest.raises(InvalidReadingError) as exc:
        await IngestReading(repo).execute(make_command(value=500.0))

    assert exc.value.field == "value"
    assert repo.readings == []
