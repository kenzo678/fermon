from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from fermon.fermentation.application import GetLabAnalysis, ListLabAnalyses, RecordLabAnalysis
from fermon.fermentation.domain import (
    Batch,
    BatchStatus,
    QualityParameter,
    QualityProfile,
    QualitySpec,
    QualityStage,
    SpecRange,
    StyleTemplate,
    TargetRanges,
)
from fermon.fermentation.infrastructure.http.dependencies import (
    get_get_lab_analysis,
    get_list_lab_analyses,
    get_record_lab_analysis,
)
from fermon.main import create_app
from tests.auth_helpers import CSRF_HEADERS, role_headers, sign_in_fake_sessions
from tests.fermentation.fakes import (
    InMemoryBatchRepository,
    InMemoryLabAnalysisRepository,
    InMemoryQualityProfileRepository,
)

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
NOW = T0 + timedelta(hours=6)
PROFILE_ID = UUID(int=500)
LINKED, PLANNED = UUID(int=1), UUID(int=3)
OE_SPEC = QualitySpec(
    QualityStage.BREWHOUSE,
    QualityParameter.ORIGINAL_EXTRACT,
    SpecRange(9.9, 10.5),
    SpecRange(10.0, 10.4),
)


class Ids:
    def __init__(self) -> None:
        self.n = 100

    def __call__(self) -> UUID:
        self.n += 1
        return UUID(int=self.n)


def batch(batch_id: UUID, **overrides: Any) -> Batch:
    values: dict[str, Any] = {
        "id": batch_id,
        "tank_id": f"tank-{batch_id.int}",
        "beer_name": "Pale Lager",
        "style": "Lager",
        "template": StyleTemplate.LAGER,
        "targets": TargetRanges(8.0, 12.0, 1.2),
        "status": BatchStatus.ACTIVE,
        "planned_start": T0,
        "started_at": T0,
        "created_at": T0,
    }
    return Batch(**{**values, **overrides})


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    batches = InMemoryBatchRepository()
    profiles = InMemoryQualityProfileRepository()
    analyses = InMemoryLabAnalysisRepository(batches)
    await profiles.add(
        QualityProfile(id=PROFILE_ID, name="Pale lager", created_at=T0, specs=(OE_SPEC,))
    )
    await batches.add(batch(LINKED, quality_profile_id=PROFILE_ID))
    await batches.add(batch(PLANNED, status=BatchStatus.PLANNED, started_at=None))
    ids = Ids()

    app: FastAPI = create_app()

    sign_in_fake_sessions(app)
    overrides: Any = app.dependency_overrides
    overrides[get_record_lab_analysis] = lambda: RecordLabAnalysis(
        batches, profiles, analyses, lambda: NOW, ids
    )
    overrides[get_list_lab_analyses] = lambda: ListLabAnalyses(batches, analyses)
    overrides[get_get_lab_analysis] = lambda: GetLabAnalysis(analyses)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=CSRF_HEADERS
    ) as client:
        yield client


def body(**overrides: Any) -> dict[str, Any]:
    return {"stage": "brewhouse", "values": {"original_extract": 10.45, "ph": 5.2}, **overrides}


async def post(client: AsyncClient, batch_id: UUID = LINKED, **overrides: Any) -> Any:
    return await client.post(f"/batches/{batch_id}/lab-analyses", json=body(**overrides))


def error_fields(response: Any) -> list[str | None]:
    return [d["field"] for d in response.json()["detail"]]


async def test_record_returns_201_with_judged_results(client: AsyncClient) -> None:
    response = await post(
        client, sampled_at="2026-01-01T14:30:00-03:00", analyst="M. Ruiz", notes="after fill"
    )

    assert response.status_code == 201
    assert response.json() == {
        "id": str(UUID(int=101)),
        "batch_id": str(LINKED),
        "stage": "brewhouse",
        "sampled_at": "2026-01-01T17:30:00Z",
        "created_at": "2026-01-01T18:00:00Z",
        "analyst": "M. Ruiz",
        "notes": "after fill",
        "quality_profile_id": str(PROFILE_ID),
        "results": [
            {"parameter": "original_extract", "value": 10.45, "unit": "°P", "status": "warning"},
            {"parameter": "ph", "value": 5.2, "unit": "pH", "status": "no_spec"},
        ],
    }


async def test_sampled_at_defaults_to_now(client: AsyncClient) -> None:
    response = await post(client)

    assert response.json()["sampled_at"] == "2026-01-01T18:00:00Z"


async def test_invalid_analyses_name_the_field(client: AsyncClient) -> None:
    cases = [
        ({"values": {}}, ["values"]),
        ({"values": {"gravity": 1.0}}, ["values.gravity"]),
        ({"values": {"ph": 15}}, ["values.ph"]),
        ({"stage": "mash"}, ["stage"]),
        ({"sampled_at": "2026-01-01T19:00:00Z"}, ["sampled_at"]),
        ({"warning": True}, ["warning"]),
    ]
    for overrides, fields in cases:
        response = await post(client, **overrides)

        assert response.status_code == 422, overrides
        assert error_fields(response) == fields, overrides


async def test_unknown_batch_is_not_found_and_planned_batch_is_a_conflict(
    client: AsyncClient,
) -> None:
    unknown = await post(client, UUID(int=99))
    planned = await post(client, PLANNED)

    assert (unknown.status_code, error_fields(unknown)) == (404, ["batch_id"])
    assert (planned.status_code, error_fields(planned)) == (409, ["status"])


async def test_list_orders_by_sample_time_and_filters_by_stage(client: AsyncClient) -> None:
    late = (await post(client, sampled_at="2026-01-01T17:00:00Z")).json()
    early = (await post(client, sampled_at="2026-01-01T13:00:00Z")).json()
    packaged = (await post(client, stage="packaged", sampled_at="2026-01-01T15:00:00Z")).json()
    path = f"/batches/{LINKED}/lab-analyses"

    every = await client.get(path)
    brewhouse = await client.get(path, params={"stage": "brewhouse"})

    assert [a["id"] for a in every.json()] == [early["id"], packaged["id"], late["id"]]
    assert [a["id"] for a in brewhouse.json()] == [early["id"], late["id"]]
    assert every.json()[0] == early


async def test_list_rejects_an_unknown_stage_or_batch(client: AsyncClient) -> None:
    bad_stage = await client.get(f"/batches/{LINKED}/lab-analyses", params={"stage": "mash"})
    unknown = await client.get(f"/batches/{UUID(int=99)}/lab-analyses")

    assert (bad_stage.status_code, error_fields(bad_stage)) == (422, ["stage"])
    assert (unknown.status_code, error_fields(unknown)) == (404, ["batch_id"])


async def test_get_one_analysis(client: AsyncClient) -> None:
    created = (await post(client)).json()

    found = await client.get(f"/lab-analyses/{created['id']}")
    unknown = await client.get(f"/lab-analyses/{UUID(int=99)}")
    malformed = await client.get("/lab-analyses/not-a-uuid")

    assert (found.status_code, found.json()) == (200, created)
    assert (unknown.status_code, error_fields(unknown)) == (404, ["analysis_id"])
    assert (malformed.status_code, error_fields(malformed)) == (422, ["analysis_id"])


async def test_a_viewer_reads_analyses_but_cannot_record_them(client: AsyncClient) -> None:
    viewer = role_headers("viewer")
    created = (await post(client)).json()

    recorded = await client.post(f"/batches/{LINKED}/lab-analyses", json=body(), headers=viewer)
    found = await client.get(f"/lab-analyses/{created['id']}", headers=viewer)
    listed = await client.get(f"/batches/{LINKED}/lab-analyses", headers=viewer)

    assert recorded.status_code == 403
    assert found.status_code == 200
    assert [a["id"] for a in listed.json()] == [created["id"]]
