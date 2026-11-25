from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from fermon.fermentation.application import BuildBatchReport
from fermon.fermentation.domain import (
    Batch,
    BatchStatus,
    MeasurementType,
    Reading,
    StyleTemplate,
    TargetRanges,
)
from fermon.fermentation.infrastructure.http.dependencies import get_build_batch_report
from fermon.main import create_app
from tests.auth_helpers import ANONYMOUS, CSRF_HEADERS, role_headers, sign_in_fake_sessions
from tests.fermentation.fakes import (
    InMemoryAlertRepository,
    InMemoryBatchRepository,
    InMemoryLabAnalysisRepository,
    InMemoryQualityProfileRepository,
    InMemoryReadingRepository,
)

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
NOW = T0 + timedelta(hours=3)
FINISHED, ACTIVE, PLANNED = UUID(int=1), UUID(int=2), UUID(int=3)


def batch(batch_id: UUID, status: BatchStatus, tank: str) -> Batch:
    return Batch(
        id=batch_id,
        tank_id=tank,
        beer_name="Pale Ale",
        style="APA",
        template=StyleTemplate.ALE,
        targets=TargetRanges(18.0, 21.0, 1.0, None, 5.0),
        status=status,
        planned_start=T0 - timedelta(days=1),
        created_at=T0 - timedelta(days=2),
        started_at=None if status is BatchStatus.PLANNED else T0,
        finished_at=T0 + timedelta(hours=2) if status is BatchStatus.FINISHED else None,
    )


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    batches, readings = InMemoryBatchRepository(), InMemoryReadingRepository()
    await batches.add(batch(FINISHED, BatchStatus.FINISHED, "tank-1"))
    await batches.add(batch(ACTIVE, BatchStatus.ACTIVE, "tank-2"))
    await batches.add(batch(PLANNED, BatchStatus.PLANNED, "tank-3"))
    for tank in ("tank-1", "tank-2"):
        for minute in range(0, 100, 5):
            at = T0 + timedelta(minutes=minute)
            m = MeasurementType.TEMPERATURE
            await readings.add(Reading(tank, "s1", m, 19.0 + minute % 3, m.unit, at))
    app = create_app()
    sign_in_fake_sessions(app)
    overrides: Any = app.dependency_overrides
    overrides[get_build_batch_report] = lambda: BuildBatchReport(
        batches,
        readings,
        InMemoryAlertRepository(),
        InMemoryLabAnalysisRepository(batches),
        InMemoryQualityProfileRepository(),
        clock=lambda: NOW,
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=CSRF_HEADERS
    ) as client:
        yield client


async def test_the_pdf_is_an_attachment_named_after_the_beer_and_the_date(
    client: AsyncClient,
) -> None:
    response = await client.get(f"/batches/{FINISHED}/report.pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == (
        'attachment; filename="batch-pale-ale-2026-01-01.pdf"'
    )
    assert response.content.startswith(b"%PDF-")


async def test_the_csv_is_an_attachment_with_the_summary_and_statistics(
    client: AsyncClient,
) -> None:
    response = await client.get(f"/batches/{FINISHED}/report.csv")

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.headers["content-disposition"] == (
        'attachment; filename="batch-pale-ale-2026-01-01.csv"'
    )
    assert "beer_name,Pale Ale" in response.text
    assert "temperature,celsius,20," in response.text


async def test_an_active_batch_downloads_a_partial_report(client: AsyncClient) -> None:
    response = await client.get(f"/batches/{ACTIVE}/report.csv")

    assert response.status_code == 200
    assert "report,Partial (batch in progress)" in response.text


@pytest.mark.parametrize("role", ["viewer", "brewer", "admin"])
@pytest.mark.parametrize("extension", ["pdf", "csv"])
async def test_every_role_can_download(client: AsyncClient, role: str, extension: str) -> None:
    response = await client.get(
        f"/batches/{FINISHED}/report.{extension}", headers=role_headers(role)
    )

    assert response.status_code == 200


@pytest.mark.parametrize("extension", ["pdf", "csv"])
async def test_a_session_is_required(client: AsyncClient, extension: str) -> None:
    response = await client.get(
        f"/batches/{FINISHED}/report.{extension}", headers=role_headers(ANONYMOUS)
    )

    assert response.status_code == 401


@pytest.mark.parametrize("extension", ["pdf", "csv"])
async def test_an_unknown_batch_is_404_on_batch_id(client: AsyncClient, extension: str) -> None:
    response = await client.get(f"/batches/{UUID(int=99)}/report.{extension}")

    assert response.status_code == 404
    assert response.json()["detail"][0]["field"] == "batch_id"


@pytest.mark.parametrize("extension", ["pdf", "csv"])
async def test_a_planned_batch_is_409_on_status(client: AsyncClient, extension: str) -> None:
    response = await client.get(f"/batches/{PLANNED}/report.{extension}")

    assert response.status_code == 409
    assert response.json()["detail"][0]["field"] == "status"


async def test_a_malformed_batch_id_is_422(client: AsyncClient) -> None:
    response = await client.get("/batches/not-a-uuid/report.pdf")

    assert response.status_code == 422
