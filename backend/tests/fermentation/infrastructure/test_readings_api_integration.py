from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from fermon.main import create_app
from fermon.shared.config import Settings

pytestmark = pytest.mark.integration

BODY = {
    "tank_id": "tank-1",
    "sensor_id": "probe-a",
    "measurement": "temperature",
    "value": 18.5,
    "unit": "celsius",
    "recorded_at": "2026-01-01T10:00:00Z",
}
RANGE = {"start": "2026-01-01T00:00:00Z", "end": "2026-01-02T00:00:00Z"}


@pytest_asyncio.fixture
async def client(engine: AsyncEngine, migrated_database_url: str) -> AsyncIterator[AsyncClient]:
    """Real app (real lifespan, real repository) wired to the test database only."""
    app: FastAPI = create_app(Settings(database_url=migrated_database_url))
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


async def test_post_then_get_round_trip(client: AsyncClient) -> None:
    created = await client.post("/readings", json=BODY)
    listed = await client.get("/tanks/tank-1/readings", params=RANGE)

    assert created.status_code == 201
    assert listed.status_code == 200
    assert listed.json() == [created.json()]
    assert listed.json()[0]["value"] == 18.5


async def test_duplicate_post_returns_the_first_value_and_keeps_a_single_row(
    client: AsyncClient, engine: AsyncEngine
) -> None:
    first = await client.post("/readings", json=BODY)
    second = await client.post("/readings", json={**BODY, "value": 19.0})

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json() == first.json()
    assert second.json()["value"] == 18.5
    async with engine.connect() as conn:
        assert await conn.scalar(text("SELECT count(*) FROM readings")) == 1


@pytest.mark.parametrize(
    ("offset_timestamp", "utc_timestamp"),
    [
        ("2026-01-01T12:00:00+02:00", "2026-01-01T10:00:00Z"),
        ("2026-01-01T07:00:00-03:00", "2026-01-01T10:00:00Z"),
    ],
)
async def test_non_utc_offsets_are_answered_normalized_to_utc_in_post_and_get(
    client: AsyncClient, offset_timestamp: str, utc_timestamp: str
) -> None:
    created = await client.post("/readings", json={**BODY, "recorded_at": offset_timestamp})
    listed = await client.get("/tanks/tank-1/readings", params=RANGE)

    assert created.status_code == 201
    assert created.json()["recorded_at"] == utc_timestamp
    assert listed.json() == [created.json()]


async def test_ingest_registers_the_tank_once_and_tanks_endpoints_show_latest_readings(
    client: AsyncClient, engine: AsyncEngine
) -> None:
    await client.post("/readings", json=BODY)
    await client.post(
        "/readings", json={**BODY, "value": 19.0, "recorded_at": "2026-01-01T11:00:00Z"}
    )
    await client.post("/readings", json=BODY)  # duplicate

    listed = await client.get("/tanks")
    single = await client.get("/tanks/tank-1")
    missing = await client.get("/tanks/nope")

    assert listed.status_code == 200
    [tank] = listed.json()
    assert tank["id"] == "tank-1"
    assert tank["first_seen_at"] == "2026-01-01T10:00:00Z"
    assert tank["latest"]["temperature"]["value"] == 19.0
    assert tank["latest"]["pressure"] is None
    assert single.json() == tank
    assert missing.status_code == 404
    async with engine.connect() as conn:
        assert await conn.scalar(text("SELECT count(*) FROM tanks")) == 1
