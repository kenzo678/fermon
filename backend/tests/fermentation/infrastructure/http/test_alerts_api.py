from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from fermon.fermentation.application import AcknowledgeAlert, GetAlert, ListAlerts
from fermon.fermentation.domain import Alert, AlertKind, AlertStatus, MeasurementType
from fermon.fermentation.infrastructure.http.dependencies import (
    get_acknowledge_alert,
    get_get_alert,
    get_list_alerts,
)
from fermon.main import create_app
from tests.fermentation.fakes import InMemoryAlertRepository

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
NOW = T0 + timedelta(hours=1)
BATCH = UUID(int=1)
DETAILS = {"observed": 25.5, "bound": "above", "target_min": 18.0, "target_max": 21.0}


def make_alert(n: int, tank: str = "tank-1", **overrides: Any) -> Alert:
    values: dict[str, Any] = {
        "id": UUID(int=n),
        "tank_id": tank,
        "batch_id": BATCH,
        "kind": AlertKind.OUT_OF_RANGE,
        "measurement": MeasurementType.TEMPERATURE,
        "status": AlertStatus.OPEN,
        "opened_at": T0 + timedelta(minutes=n),
        "details": DETAILS,
    }
    return Alert(**{**values, **overrides})


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    alerts = InMemoryAlertRepository()
    local = timezone(timedelta(hours=-3))
    await alerts.add(make_alert(1, opened_at=datetime(2026, 1, 1, 9, 1, tzinfo=local)))
    await alerts.add(
        make_alert(
            2,
            kind=AlertKind.SILENT_SENSOR,
            measurement=None,
            details={"last_reading_at": None},
        )
    )
    await alerts.add(
        make_alert(
            3,
            "tank-2",
            status=AlertStatus.RESOLVED,
            resolved_at=T0 + timedelta(minutes=30),
            version=2,
        )
    )
    app: FastAPI = create_app()
    overrides: Any = app.dependency_overrides
    overrides[get_list_alerts] = lambda: ListAlerts(alerts)
    overrides[get_get_alert] = lambda: GetAlert(alerts)
    overrides[get_acknowledge_alert] = lambda: AcknowledgeAlert(alerts, lambda: NOW)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


ALERT_1 = {
    "id": str(UUID(int=1)),
    "tank_id": "tank-1",
    "batch_id": str(BATCH),
    "kind": "out_of_range",
    "measurement": "temperature",
    "status": "open",
    "opened_at": "2026-01-01T12:01:00Z",
    "acknowledged_at": None,
    "resolved_at": None,
    "details": DETAILS,
    "version": 1,
}


async def test_list_defaults_to_unresolved_newest_first_in_the_alert_shape(
    client: AsyncClient,
) -> None:
    response = await client.get("/alerts")

    assert response.status_code == 200
    second, first = response.json()
    assert first == ALERT_1  # opened_at normalized to UTC
    assert second["id"] == str(UUID(int=2))
    assert second["measurement"] is None and second["kind"] == "silent_sensor"


async def test_list_filters_by_tank_batch_kind_and_repeatable_status(client: AsyncClient) -> None:
    async def ids(query: str) -> list[int]:
        response = await client.get(f"/alerts?{query}")
        assert response.status_code == 200
        return [UUID(a["id"]).int for a in response.json()]

    assert await ids("tank_id=tank-2") == []  # its only alert is resolved
    assert await ids("tank_id=tank-2&status=resolved") == [3]
    assert await ids("status=resolved&status=open") == [3, 2, 1]
    assert await ids("kind=silent_sensor") == [2]
    assert await ids(f"batch_id={BATCH}") == [2, 1]
    assert await ids("limit=1") == [2]


async def test_list_rejects_bad_filters_with_the_unified_422(client: AsyncClient) -> None:
    for query, field in [
        ("status=closed", "status"),
        ("kind=loud", "kind"),
        ("limit=0", "limit"),
        ("limit=501", "limit"),
        ("batch_id=nope", "batch_id"),
    ]:
        response = await client.get(f"/alerts?{query}")

        assert response.status_code == 422, query
        # a repeated query parameter is located by its index: "status.0"
        assert response.json()["detail"][0]["field"].split(".")[0] == field, query
    blank = await client.get("/alerts?tank_id=%20")
    assert blank.status_code == 422
    assert blank.json()["detail"][0]["field"] == "tank_id"


async def test_get_alert_and_unknown_alert_404(client: AsyncClient) -> None:
    ok = await client.get(f"/alerts/{UUID(int=1)}")
    missing = await client.get(f"/alerts/{UUID(int=99)}")

    assert ok.status_code == 200 and ok.json() == ALERT_1
    assert missing.status_code == 404
    assert missing.json()["detail"] == [
        {"field": "alert_id", "message": f"alert '{UUID(int=99)}' not found"}
    ]


async def test_acknowledge_without_a_body_stamps_the_time_and_bumps_the_version(
    client: AsyncClient,
) -> None:
    response = await client.post(f"/alerts/{UUID(int=1)}/acknowledge")

    assert response.status_code == 200
    assert response.json() == {
        **ALERT_1,
        "status": "acknowledged",
        "acknowledged_at": "2026-01-01T13:00:00Z",
        "version": 2,
    }


async def test_acknowledge_is_idempotent(client: AsyncClient) -> None:
    first = await client.post(f"/alerts/{UUID(int=1)}/acknowledge")
    again = await client.post(f"/alerts/{UUID(int=1)}/acknowledge", json={})

    assert again.status_code == 200 and again.json() == first.json()


async def test_acknowledge_conflicts_use_the_unified_409(client: AsyncClient) -> None:
    resolved = await client.post(f"/alerts/{UUID(int=3)}/acknowledge")
    stale = await client.post(f"/alerts/{UUID(int=1)}/acknowledge", json={"version": 5})

    assert resolved.status_code == 409
    assert resolved.json()["detail"][0]["field"] == "status"
    assert stale.status_code == 409
    assert stale.json()["detail"][0]["field"] == "version"
    assert (await client.get(f"/alerts/{UUID(int=1)}")).json()["status"] == "open"
    ok = await client.post(f"/alerts/{UUID(int=1)}/acknowledge", json={"version": 1})
    assert ok.status_code == 200


async def test_acknowledge_validates_the_body_and_the_alert(client: AsyncClient) -> None:
    unknown = await client.post(f"/alerts/{UUID(int=99)}/acknowledge")
    bad = await client.post(f"/alerts/{UUID(int=1)}/acknowledge", json={"version": 0})
    extra = await client.post(f"/alerts/{UUID(int=1)}/acknowledge", json={"note": "x"})

    assert unknown.status_code == 404
    assert bad.status_code == 422 and bad.json()["detail"][0]["field"] == "version"
    assert extra.status_code == 422
