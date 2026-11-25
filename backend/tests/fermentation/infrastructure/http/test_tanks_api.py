from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from fermon.fermentation.application import (
    GetTank,
    IngestReading,
    IngestReadingCommand,
    ListTanks,
    RenameTank,
)
from fermon.fermentation.domain import Alert, AlertKind, AlertStatus, MeasurementType
from fermon.fermentation.infrastructure.http.dependencies import (
    get_get_tank,
    get_ingest_reading,
    get_list_tanks,
    get_rename_tank,
)
from fermon.main import create_app
from tests.auth_helpers import CSRF_HEADERS, role_headers, sign_in_fake_sessions
from tests.fermentation.fakes import (
    InMemoryAlertRepository,
    InMemoryBatchRepository,
    InMemoryReadingRepository,
    InMemoryTankRepository,
)

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    readings, tanks = InMemoryReadingRepository(), InMemoryTankRepository()
    batches, alerts = InMemoryBatchRepository(), InMemoryAlertRepository()
    app: FastAPI = create_app()
    sign_in_fake_sessions(app)
    app.dependency_overrides[get_ingest_reading] = lambda: IngestReading(readings, tanks)
    app.dependency_overrides[get_list_tanks] = lambda: ListTanks(tanks, readings, batches, alerts)
    app.dependency_overrides[get_get_tank] = lambda: GetTank(tanks, readings, batches, alerts)
    app.dependency_overrides[get_rename_tank] = lambda: RenameTank(
        tanks, GetTank(tanks, readings, batches, alerts)
    )
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
    temp, pressure = MeasurementType.TEMPERATURE, MeasurementType.PRESSURE
    opened = [
        Alert(UUID(int=n), "tank-2", UUID(int=1), AlertKind.OUT_OF_RANGE, m, AlertStatus.OPEN, T0)
        for n, m in ((1, temp), (2, pressure), (3, pressure))
    ]
    await alerts.add(opened[0])
    await alerts.add(opened[1].acknowledge(T0))
    await alerts.add(opened[2].resolve(T0))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=CSRF_HEADERS
    ) as client:
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
    "active_batch": None,
    "open_alerts": 0,
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


async def test_tanks_report_their_unresolved_alert_count(client: AsyncClient) -> None:
    listed = {t["id"]: t["open_alerts"] for t in (await client.get("/tanks")).json()}
    one = await client.get("/tanks/tank-2")

    assert listed == {"tank-1": 0, "tank-2": 2}  # open + acknowledged count, resolved does not
    assert one.json()["open_alerts"] == 2


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


async def test_a_viewer_can_read_tanks(client: AsyncClient) -> None:
    response = await client.get("/tanks", headers=role_headers("viewer"))

    assert response.status_code == 200


async def test_admin_renames_a_tank_and_gets_the_same_shape(client: AsyncClient) -> None:
    response = await client.patch(
        "/tanks/tank-1", json={"display_name": "  Fermenter 1 "}, headers=role_headers("admin")
    )

    assert response.status_code == 200
    assert response.json() == {**TANK_1, "display_name": "Fermenter 1"}
    assert (await client.get("/tanks/tank-1")).json()["display_name"] == "Fermenter 1"
    listed = {t["id"]: t["display_name"] for t in (await client.get("/tanks")).json()}
    assert listed == {"tank-1": "Fermenter 1", "tank-2": None}


async def test_a_null_display_name_clears_the_name(client: AsyncClient) -> None:
    headers = role_headers("admin")
    await client.patch("/tanks/tank-1", json={"display_name": "Fermenter 1"}, headers=headers)

    response = await client.patch("/tanks/tank-1", json={"display_name": None}, headers=headers)

    assert response.status_code == 200
    assert response.json()["display_name"] is None


@pytest.mark.parametrize("role", ["viewer", "brewer"])
async def test_only_an_admin_can_rename_a_tank(client: AsyncClient, role: str) -> None:
    response = await client.patch(
        "/tanks/tank-1", json={"display_name": "Fermenter 1"}, headers=role_headers(role)
    )

    assert response.status_code == 403
    assert (await client.get("/tanks/tank-1")).json()["display_name"] is None


async def test_renaming_without_a_session_is_401(client: AsyncClient) -> None:
    response = await client.patch(
        "/tanks/tank-1", json={"display_name": "Fermenter 1"}, headers=role_headers("anonymous")
    )

    assert response.status_code == 401


async def test_renaming_an_unknown_tank_returns_404_on_tank_id(client: AsyncClient) -> None:
    response = await client.patch(
        "/tanks/nope", json={"display_name": "Fermenter 1"}, headers=role_headers("admin")
    )

    assert response.status_code == 404
    [error] = response.json()["detail"]
    assert error == {"field": "tank_id", "message": "tank 'nope' not found"}


@pytest.mark.parametrize("name", ["", "   ", "a" * 65])
async def test_renaming_to_an_empty_or_too_long_name_returns_422(
    client: AsyncClient, name: str
) -> None:
    response = await client.patch(
        "/tanks/tank-1", json={"display_name": name}, headers=role_headers("admin")
    )

    assert response.status_code == 422
    [error] = response.json()["detail"]
    assert error["field"] == "display_name"


@pytest.mark.parametrize(
    "body", [{"display_name": "Fermenter 1", "id": "x"}, {}, {"display_name": 5}]
)
async def test_renaming_rejects_unknown_missing_or_mistyped_fields(
    client: AsyncClient, body: dict[str, Any]
) -> None:
    response = await client.patch("/tanks/tank-1", json=body, headers=role_headers("admin"))

    assert response.status_code == 422


async def test_renaming_requires_the_csrf_header(client: AsyncClient) -> None:
    client.headers.pop("X-Requested-With")

    response = await client.patch(
        "/tanks/tank-1", json={"display_name": "Fermenter 1"}, headers=role_headers("admin")
    )

    assert response.status_code == 403
