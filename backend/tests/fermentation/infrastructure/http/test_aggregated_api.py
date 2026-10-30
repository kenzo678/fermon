from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from fermon.fermentation.application import (
    IngestReading,
    IngestReadingCommand,
    ListAggregatedReadings,
)
from fermon.fermentation.infrastructure.http.dependencies import (
    get_ingest_reading,
    get_list_aggregated_readings,
)
from fermon.main import create_app
from tests.fermentation.fakes import InMemoryReadingRepository, InMemoryTankRepository

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
URL = "/tanks/tank-1/readings/aggregated"
RANGE = {"start": "2026-01-01T12:00:00Z", "end": "2026-01-01T13:00:00Z"}


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    readings, tanks = InMemoryReadingRepository(), InMemoryTankRepository()
    app = create_app()
    app.dependency_overrides[get_list_aggregated_readings] = lambda: ListAggregatedReadings(
        tanks, readings
    )
    ingest = IngestReading(readings, tanks)
    for measurement, unit, value, seconds in [
        ("temperature", "celsius", 18.0, 0),
        ("temperature", "celsius", 20.0, 30),
        ("temperature", "celsius", 30.0, 61),
        ("pressure", "bar", 1.5, 5),
    ]:
        await ingest.execute(
            IngestReadingCommand(
                "tank-1", "s1", measurement, value, unit, T0 + timedelta(seconds=seconds)
            )
        )
    app.dependency_overrides[get_ingest_reading] = lambda: ingest
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def test_returns_series_grouped_by_measurement_ascending_in_utc(
    client: AsyncClient,
) -> None:
    response = await client.get(URL, params={"bucket": "1m", **RANGE})

    assert response.status_code == 200
    assert response.json() == {
        "tank_id": "tank-1",
        "bucket": "1m",
        "series": {
            "temperature": [
                {
                    "bucket_start": "2026-01-01T12:00:00Z",
                    "avg": 19.0,
                    "min": 18.0,
                    "max": 20.0,
                    "count": 2,
                },
                {
                    "bucket_start": "2026-01-01T12:01:00Z",
                    "avg": 30.0,
                    "min": 30.0,
                    "max": 30.0,
                    "count": 1,
                },
            ],
            "pressure": [
                {
                    "bucket_start": "2026-01-01T12:00:00Z",
                    "avg": 1.5,
                    "min": 1.5,
                    "max": 1.5,
                    "count": 1,
                }
            ],
            "alcohol": [],
        },
    }


async def test_measurement_filter_is_repeatable_and_limits_the_series(
    client: AsyncClient,
) -> None:
    response = await client.get(
        URL, params={"bucket": "1h", "measurement": ["pressure", "alcohol"], **RANGE}
    )

    assert response.status_code == 200
    series = response.json()["series"]
    assert set(series) == {"pressure", "alcohol"}
    assert series["pressure"][0]["count"] == 1
    assert series["alcohol"] == []


async def test_unknown_tank_returns_unified_404(client: AsyncClient) -> None:
    response = await client.get("/tanks/nope/readings/aggregated", params={"bucket": "1m", **RANGE})

    assert response.status_code == 404
    assert response.json()["detail"] == [{"field": "tank_id", "message": "tank 'nope' not found"}]


async def test_invalid_bucket_measurement_or_missing_range_return_422(
    client: AsyncClient,
) -> None:
    for params, field in [
        ({"bucket": "5m", **RANGE}, "bucket"),
        ({**RANGE}, "bucket"),
        ({"bucket": "1m", "measurement": "salinity", **RANGE}, "measurement.0"),
        ({"bucket": "1m", "end": RANGE["end"]}, "start"),
        ({"bucket": "1m", "start": "2026-01-01T12:00:00", "end": RANGE["end"]}, "start"),
    ]:
        response = await client.get(URL, params=params)

        assert response.status_code == 422, params
        assert response.json()["detail"][0]["field"] == field, params


async def test_inverted_range_and_too_many_points_return_422(client: AsyncClient) -> None:
    inverted = await client.get(
        URL, params={"bucket": "1m", "start": RANGE["end"], "end": RANGE["start"]}
    )
    too_many = await client.get(
        URL, params={"bucket": "1m", "start": "2026-01-01T00:00:00Z", "end": "2026-02-01T00:00:00Z"}
    )

    assert inverted.status_code == 422
    assert "start must be before end" in inverted.json()["detail"][0]["message"]
    assert too_many.status_code == 422
    assert "range too large" in too_many.json()["detail"][0]["message"]
