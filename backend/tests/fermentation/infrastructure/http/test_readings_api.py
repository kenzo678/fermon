from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from fermon.fermentation.application.ingest_reading import IngestReading
from fermon.fermentation.application.list_readings import ListReadings
from fermon.fermentation.infrastructure.http.dependencies import (
    get_ingest_reading,
    get_list_readings,
)
from fermon.main import create_app
from tests.fermentation.fakes import InMemoryReadingRepository, InMemoryTankRepository


def make_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "tank_id": "tank-1",
        "sensor_id": "probe-a",
        "measurement": "temperature",
        "value": 18.5,
        "unit": "celsius",
        "recorded_at": "2026-01-01T10:00:00Z",
    }
    body.update(overrides)
    return body


@pytest.fixture
def repository() -> InMemoryReadingRepository:
    return InMemoryReadingRepository()


@pytest.fixture
def app(repository: InMemoryReadingRepository) -> FastAPI:
    app = create_app()
    app.dependency_overrides[get_ingest_reading] = lambda: IngestReading(
        repository, InMemoryTankRepository()
    )
    app.dependency_overrides[get_list_readings] = lambda: ListReadings(repository)
    return app


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def test_post_valid_reading_returns_201_with_reading(client: AsyncClient) -> None:
    response = await client.post("/readings", json=make_body())

    assert response.status_code == 201
    assert response.json() == {
        "tank_id": "tank-1",
        "sensor_id": "probe-a",
        "measurement": "temperature",
        "value": 18.5,
        "unit": "celsius",
        "recorded_at": "2026-01-01T10:00:00Z",
    }


async def test_post_stores_the_reading(
    client: AsyncClient, repository: InMemoryReadingRepository
) -> None:
    await client.post("/readings", json=make_body())

    assert [r.tank_id for r in repository.readings] == ["tank-1"]


async def test_post_duplicate_returns_200_with_the_first_stored_reading(
    client: AsyncClient, repository: InMemoryReadingRepository
) -> None:
    first = await client.post("/readings", json=make_body(value=18.5))
    second = await client.post("/readings", json=make_body(value=19.0))

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json() == first.json()
    assert second.json()["value"] == 18.5
    assert len(repository.readings) == 1


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"measurement": "humidity"}, "measurement"),
        ({"value": 150.0}, "value"),
        ({"unit": "fahrenheit"}, "unit"),
        ({"tank_id": "   "}, "tank_id"),
    ],
)
async def test_post_domain_violation_returns_422_with_field(
    client: AsyncClient, overrides: dict[str, Any], field: str
) -> None:
    response = await client.post("/readings", json=make_body(**overrides))

    assert response.status_code == 422
    (error,) = response.json()["detail"]
    assert error["field"] == field
    assert isinstance(error["message"], str)


async def test_post_naive_datetime_returns_unified_422(client: AsyncClient) -> None:
    response = await client.post("/readings", json=make_body(recorded_at="2026-01-01T10:00:00"))

    assert response.status_code == 422
    (error,) = response.json()["detail"]
    assert error["field"] == "recorded_at"
    assert isinstance(error["message"], str)


async def test_post_extra_field_returns_unified_422(client: AsyncClient) -> None:
    response = await client.post("/readings", json=make_body(color="red"))

    assert response.status_code == 422
    (error,) = response.json()["detail"]
    assert error["field"] == "color"
    assert isinstance(error["message"], str)


async def test_post_missing_field_returns_unified_422(client: AsyncClient) -> None:
    body = make_body()
    del body["value"]

    response = await client.post("/readings", json=body)

    assert response.status_code == 422
    (error,) = response.json()["detail"]
    assert error["field"] == "value"
    assert isinstance(error["message"], str)


async def test_get_returns_tank_readings_in_range_ordered_end_exclusive(
    client: AsyncClient,
) -> None:
    for recorded_at, tank in [
        ("2026-01-01T12:00:00Z", "tank-1"),
        ("2026-01-01T10:00:00Z", "tank-1"),
        ("2026-01-01T11:00:00Z", "tank-1"),
        ("2026-01-01T13:00:00Z", "tank-1"),  # end bound: excluded
        ("2026-01-01T11:30:00Z", "tank-2"),  # other tank
        ("2026-01-01T09:59:00Z", "tank-1"),  # before start
    ]:
        await client.post("/readings", json=make_body(tank_id=tank, recorded_at=recorded_at))

    response = await client.get(
        "/tanks/tank-1/readings",
        params={"start": "2026-01-01T10:00:00Z", "end": "2026-01-01T13:00:00Z"},
    )

    assert response.status_code == 200
    assert [r["recorded_at"] for r in response.json()] == [
        "2026-01-01T10:00:00Z",
        "2026-01-01T11:00:00Z",
        "2026-01-01T12:00:00Z",
    ]


async def test_get_empty_range_returns_empty_list(client: AsyncClient) -> None:
    response = await client.get(
        "/tanks/tank-1/readings",
        params={"start": "2026-01-01T10:00:00Z", "end": "2026-01-01T13:00:00Z"},
    )

    assert response.status_code == 200
    assert response.json() == []


async def test_get_inverted_range_returns_422(client: AsyncClient) -> None:
    response = await client.get(
        "/tanks/tank-1/readings",
        params={"start": "2026-01-01T13:00:00Z", "end": "2026-01-01T10:00:00Z"},
    )

    assert response.status_code == 422
    (error,) = response.json()["detail"]
    assert error["field"] is None


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"start": "2026-01-01T10:00:00Z"},
        {"end": "2026-01-01T10:00:00Z"},
        {"start": "2026-01-01T10:00:00", "end": "2026-01-01T13:00:00Z"},
    ],
)
async def test_get_missing_or_naive_params_return_422(
    client: AsyncClient, params: dict[str, str]
) -> None:
    response = await client.get("/tanks/tank-1/readings", params=params)

    assert response.status_code == 422
    errors = response.json()["detail"]
    assert errors
    assert all(set(e) == {"field", "message"} for e in errors)


async def test_get_missing_start_reports_the_start_field(client: AsyncClient) -> None:
    response = await client.get("/tanks/tank-1/readings", params={"end": "2026-01-01T13:00:00Z"})

    assert response.status_code == 422
    (error,) = response.json()["detail"]
    assert error["field"] == "start"


async def test_get_blank_tank_id_returns_422_with_field(client: AsyncClient) -> None:
    response = await client.get(
        "/tanks/%20/readings",
        params={"start": "2026-01-01T10:00:00Z", "end": "2026-01-01T13:00:00Z"},
    )

    assert response.status_code == 422
    (error,) = response.json()["detail"]
    assert error["field"] == "tank_id"


async def test_post_malformed_json_reports_no_field(client: AsyncClient) -> None:
    response = await client.post(
        "/readings", content=b'{"tank_id": ', headers={"content-type": "application/json"}
    )

    assert response.status_code == 422
    [error] = response.json()["detail"]
    assert error["field"] is None
