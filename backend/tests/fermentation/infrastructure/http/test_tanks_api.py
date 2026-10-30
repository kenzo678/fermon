from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from fermon.fermentation.application import GetTank, IngestReading, IngestReadingCommand, ListTanks
from fermon.fermentation.domain import MeasurementType
from fermon.fermentation.infrastructure.http.dependencies import (
    get_get_tank,
    get_ingest_reading,
    get_list_tanks,
)
from fermon.main import create_app
from tests.fermentation.fakes import InMemoryReadingRepository, InMemoryTankRepository

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    readings, tanks = InMemoryReadingRepository(), InMemoryTankRepository()
    app: FastAPI = create_app()
    app.dependency_overrides[get_ingest_reading] = lambda: IngestReading(readings, tanks)
    app.dependency_overrides[get_list_tanks] = lambda: ListTanks(tanks, readings)
    app.dependency_overrides[get_get_tank] = lambda: GetTank(tanks, readings)
    ingest = IngestReading(readings, tanks)
    for tank, measurement, value, at in [
        ("tank-2", MeasurementType.ALCOHOL, 4.0, T0),
        ("tank-1", MeasurementType.TEMPERATURE, 18.0, T0),
        ("tank-1", MeasurementType.TEMPERATURE, 19.5, T0 + timedelta(minutes=5)),
        ("tank-1", MeasurementType.PRESSURE, 1.2, T0.astimezone(timezone(timedelta(hours=-3)))),
    ]:
        await ingest.execute(
            IngestReadingCommand(tank, f"{tank}-s", measurement.value, value, measurement.unit, at)
        )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


def reading_json(tank: str, measurement: str, value: float, unit: str, at: str) -> dict[str, Any]:
    return {
        "tank_id": tank,
        "sensor_id": f"{tank}-s",
        "measurement": measurement,
        "value": value,
        "unit": unit,
        "recorded_at": at,
    }


TANK_1 = {
    "id": "tank-1",
    "display_name": None,
    "first_seen_at": "2026-01-01T12:00:00Z",
    "latest": {
        "temperature": reading_json(
            "tank-1", "temperature", 19.5, "celsius", "2026-01-01T12:05:00Z"
        ),
        "pressure": reading_json("tank-1", "pressure", 1.2, "bar", "2026-01-01T12:00:00Z"),
        "alcohol": None,
    },
}


async def test_list_tanks_returns_sorted_tanks_with_latest_readings_in_utc(
    client: AsyncClient,
) -> None:
    response = await client.get("/tanks")

    assert response.status_code == 200
    first, second = response.json()
    assert first == TANK_1
    assert second["id"] == "tank-2"
    assert second["latest"]["alcohol"]["value"] == 4.0
    assert second["latest"]["temperature"] is None


async def test_get_tank_returns_the_same_shape(client: AsyncClient) -> None:
    response = await client.get("/tanks/tank-1")

    assert response.status_code == 200
    assert response.json() == TANK_1


async def test_get_unknown_tank_returns_unified_404(client: AsyncClient) -> None:
    response = await client.get("/tanks/nope")

    assert response.status_code == 404
    [error] = response.json()["detail"]
    assert error == {"field": "tank_id", "message": "tank 'nope' not found"}


async def test_get_blank_tank_id_returns_422(client: AsyncClient) -> None:
    response = await client.get("/tanks/%20")

    assert response.status_code == 422
    [error] = response.json()["detail"]
    assert error["field"] == "tank_id"
