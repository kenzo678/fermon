from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from fermon.fermentation.application import (
    CreateBatch,
    FinishBatch,
    GetBatch,
    GetTank,
    ListBatches,
    ListTanks,
    StartBatch,
    UpdateBatch,
)
from fermon.fermentation.infrastructure.http.dependencies import (
    get_create_batch,
    get_finish_batch,
    get_get_batch,
    get_get_tank,
    get_list_batches,
    get_list_tanks,
    get_start_batch,
    get_update_batch,
)
from fermon.main import create_app
from tests.fermentation.fakes import (
    InMemoryBatchRepository,
    InMemoryReadingRepository,
    InMemoryTankRepository,
)

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
ALE_TARGETS = {
    "temperature_min": 18.0,
    "temperature_max": 21.0,
    "pressure_max": 1.0,
    "pressure_min": None,
    "expected_final_abv": 5.0,
}


class Ids:
    def __init__(self) -> None:
        self.n = 0

    def __call__(self) -> UUID:
        self.n += 1
        return UUID(int=self.n)


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    tanks, batches, readings = (
        InMemoryTankRepository(),
        InMemoryBatchRepository(),
        InMemoryReadingRepository(),
    )
    for tank in ("tank-1", "tank-2"):
        await tanks.ensure(tank, T0)
    now = [T0]
    ids = Ids()

    def clock() -> datetime:
        return now[0]

    app: FastAPI = create_app()
    overrides: Any = app.dependency_overrides
    overrides[get_create_batch] = lambda: CreateBatch(batches, tanks, clock, ids)
    overrides[get_update_batch] = lambda: UpdateBatch(batches)
    overrides[get_start_batch] = lambda: StartBatch(batches, clock)
    overrides[get_finish_batch] = lambda: FinishBatch(batches, clock)
    overrides[get_get_batch] = lambda: GetBatch(batches)
    overrides[get_list_batches] = lambda: ListBatches(batches)
    overrides[get_list_tanks] = lambda: ListTanks(tanks, readings, batches)
    overrides[get_get_tank] = lambda: GetTank(tanks, readings, batches)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.clock = now  # type: ignore[attr-defined]
        yield client


def body(**overrides: Any) -> dict[str, Any]:
    return {
        "tank_id": "tank-1",
        "beer_name": "Pale Ale",
        "style": "APA",
        "template": "ale",
        **overrides,
    }


async def create(client: AsyncClient, **overrides: Any) -> dict[str, Any]:
    response = await client.post("/batches", json=body(**overrides))
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


async def test_templates_list_the_presets() -> None:
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/batch-templates")

    assert response.status_code == 200
    assert response.json() == [
        {"template": "ale", "targets": ALE_TARGETS},
        {
            "template": "lager",
            "targets": {
                "temperature_min": 8.0,
                "temperature_max": 12.0,
                "pressure_max": 1.2,
                "pressure_min": None,
                "expected_final_abv": 5.2,
            },
        },
    ]


async def test_create_returns_201_with_the_batch_shape_in_utc(client: AsyncClient) -> None:
    response = await client.post(
        "/batches",
        json=body(
            planned_start="2026-01-02T09:00:00-03:00",
            expected_end="2026-01-20T12:00:00Z",
            notes="first",
        ),
    )

    assert response.status_code == 201
    assert response.json() == {
        "id": str(UUID(int=1)),
        "tank_id": "tank-1",
        "beer_name": "Pale Ale",
        "style": "APA",
        "template": "ale",
        "status": "planned",
        "targets": ALE_TARGETS,
        "planned_start": "2026-01-02T12:00:00Z",
        "expected_end": "2026-01-20T12:00:00Z",
        "started_at": None,
        "finished_at": None,
        "notes": "first",
        "created_at": "2026-01-01T12:00:00Z",
        "version": 1,
    }


async def test_create_with_explicit_targets_overrides_the_template(client: AsyncClient) -> None:
    created = await create(client, targets={"temperature_max": 22.5, "pressure_min": 0.1})

    assert created["targets"] == {**ALE_TARGETS, "temperature_max": 22.5, "pressure_min": 0.1}


async def test_create_custom_without_targets_is_422_naming_the_field(client: AsyncClient) -> None:
    response = await client.post("/batches", json=body(template="custom"))

    assert response.status_code == 422
    [error] = response.json()["detail"]
    assert error["field"] == "temperature_min"


async def test_create_validation_errors_use_the_unified_422_shape(client: AsyncClient) -> None:
    cases = [
        (body(beer_name=" "), "beer_name"),
        (body(template="ipa"), "template"),
        (body(targets={"temperature_min": 30.0}), "temperature_max"),
        (body(targets={"pressure_max": 99}), "pressure_max"),
        (body(planned_start="2026-01-02T09:00:00"), "planned_start"),
        (body(unknown=1), "unknown"),
        ({k: v for k, v in body().items() if k != "style"}, "style"),
    ]
    for payload, field in cases:
        response = await client.post("/batches", json=payload)
        assert response.status_code == 422, payload
        assert field in [e["field"] for e in response.json()["detail"]], payload


async def test_create_for_an_unknown_tank_is_404(client: AsyncClient) -> None:
    response = await client.post("/batches", json=body(tank_id="nope"))

    assert response.status_code == 404
    assert response.json()["detail"] == [{"field": "tank_id", "message": "tank 'nope' not found"}]


async def test_get_one_and_unknown_batch(client: AsyncClient) -> None:
    created = await create(client)

    found = await client.get(f"/batches/{created['id']}")
    missing = await client.get(f"/batches/{UUID(int=99)}")
    malformed = await client.get("/batches/not-a-uuid")

    assert found.status_code == 200 and found.json() == created
    assert missing.status_code == 404
    assert missing.json()["detail"][0]["field"] == "batch_id"
    assert malformed.status_code == 422


async def test_list_filters_by_tank_and_status_newest_first(client: AsyncClient) -> None:
    first = await create(client)
    client.clock[0] = T0 + timedelta(minutes=1)  # type: ignore[attr-defined]
    second = await create(client, tank_id="tank-2")
    await client.post(f"/batches/{second['id']}/start")

    everything = await client.get("/batches")
    by_tank = await client.get("/batches", params={"tank_id": "tank-1"})
    by_status = await client.get("/batches", params={"status": "active"})
    bad_status = await client.get("/batches", params={"status": "paused"})

    assert [b["id"] for b in everything.json()] == [second["id"], first["id"]]
    assert [b["id"] for b in by_tank.json()] == [first["id"]]
    assert [b["id"] for b in by_status.json()] == [second["id"]]
    assert bad_status.status_code == 422
    assert bad_status.json()["detail"][0]["field"] == "status"


async def test_patch_updates_only_the_sent_fields_and_merges_targets(client: AsyncClient) -> None:
    created = await create(client)

    response = await client.patch(
        f"/batches/{created['id']}",
        json={"notes": "dry hop", "targets": {"temperature_max": 22.0, "expected_final_abv": None}},
    )

    assert response.status_code == 200
    assert response.json() == {
        **created,
        "notes": "dry hop",
        "targets": {**ALE_TARGETS, "temperature_max": 22.0, "expected_final_abv": None},
        "version": 2,
    }


async def test_patch_that_changes_nothing_keeps_the_version(client: AsyncClient) -> None:
    created = await create(client)
    url = f"/batches/{created['id']}"

    for payload in ({"targets": None}, {"targets": {}}, {"notes": created["notes"]}):
        response = await client.patch(url, json=payload)
        assert response.status_code == 200, payload
        assert response.json() == created, payload


async def test_patch_with_a_stale_version_is_409_on_the_version_field(
    client: AsyncClient,
) -> None:
    created = await create(client)
    url = f"/batches/{created['id']}"
    await client.post(f"{url}/start")  # stored version is now 2

    stale = await client.patch(url, json={"notes": "late", "version": created["version"]})
    current = await client.patch(url, json={"notes": "fresh", "version": 2})

    assert stale.status_code == 409
    assert stale.json()["detail"][0]["field"] == "version"
    assert current.status_code == 200
    assert current.json()["notes"] == "fresh" and current.json()["version"] == 3
    assert current.json()["status"] == "active"


async def test_patch_errors(client: AsyncClient) -> None:
    created = await create(client)
    url = f"/batches/{created['id']}"

    invalid = await client.patch(url, json={"targets": {"temperature_min": 50.0}})
    cannot_move = await client.patch(url, json={"tank_id": "tank-2"})
    unknown = await client.patch(f"/batches/{UUID(int=99)}", json={"notes": "x"})
    await client.post(f"{url}/start")
    await client.post(f"{url}/finish")
    finished = await client.patch(url, json={"notes": "late"})

    assert invalid.status_code == 422
    assert invalid.json()["detail"][0]["field"] == "temperature_max"
    assert cannot_move.status_code == 422
    assert unknown.status_code == 404
    assert finished.status_code == 409
    assert finished.json()["detail"][0]["field"] == "status"


async def test_start_and_finish_stamp_times_and_report_conflicts_as_409(
    client: AsyncClient,
) -> None:
    first, second = await create(client), await create(client, beer_name="Second")
    clock: list[datetime] = client.clock  # type: ignore[attr-defined]

    clock[0] = T0 + timedelta(hours=1)
    started = await client.post(f"/batches/{first['id']}/start")
    conflict = await client.post(f"/batches/{second['id']}/start")
    again = await client.post(f"/batches/{first['id']}/start")
    premature = await client.post(f"/batches/{second['id']}/finish")
    clock[0] = T0 + timedelta(days=7)
    finished = await client.post(f"/batches/{first['id']}/finish")
    then_second = await client.post(f"/batches/{second['id']}/start")

    assert started.status_code == 200
    assert started.json()["status"] == "active"
    assert started.json()["started_at"] == "2026-01-01T13:00:00Z"
    assert conflict.status_code == 409
    assert conflict.json()["detail"] == [
        {"field": "tank_id", "message": "tank 'tank-1' already has an active batch"}
    ]
    assert again.status_code == 409 and again.json()["detail"][0]["field"] == "status"
    assert premature.status_code == 409
    assert finished.json()["status"] == "finished"
    assert finished.json()["finished_at"] == "2026-01-08T12:00:00Z"
    assert then_second.status_code == 200
    unknown = await client.post(f"/batches/{UUID(int=99)}/finish")
    assert unknown.status_code == 404


async def test_tanks_expose_the_active_batch_summary_or_null(client: AsyncClient) -> None:
    batch = await create(client, expected_end="2026-01-20T12:00:00Z")
    await create(client, tank_id="tank-2")  # planned only
    await client.post(f"/batches/{batch['id']}/start")

    listed = (await client.get("/tanks")).json()
    one = (await client.get("/tanks/tank-1")).json()
    idle = (await client.get("/tanks/tank-2")).json()

    expected = {
        "id": batch["id"],
        "beer_name": "Pale Ale",
        "style": "APA",
        "targets": ALE_TARGETS,
        "started_at": "2026-01-01T12:00:00Z",
        "expected_end": "2026-01-20T12:00:00Z",
    }
    assert listed[0]["active_batch"] == expected and one["active_batch"] == expected
    assert listed[1]["active_batch"] is None and idle["active_batch"] is None
