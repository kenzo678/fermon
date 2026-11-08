from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status
from pydantic import AwareDatetime

from fermon.fermentation.application.batches import CreateBatchCommand
from fermon.fermentation.application.ingest_reading import IngestReadingCommand
from fermon.fermentation.domain import (
    AggregationBucket,
    BatchStatus,
    MeasurementType,
    StyleTemplate,
    normalize_id,
    template_targets,
)
from fermon.fermentation.infrastructure.http.dependencies import (
    CreateBatchDep,
    FinishBatchDep,
    GetBatchDep,
    GetTankDep,
    IngestReadingDep,
    ListAggregatedReadingsDep,
    ListBatchesDep,
    ListReadingsDep,
    ListTanksDep,
    StartBatchDep,
    UpdateBatchDep,
)
from fermon.fermentation.infrastructure.http.schemas import (
    AggregatedReadingsOut,
    BatchIn,
    BatchOut,
    BatchPatch,
    BatchTemplateOut,
    ErrorResponse,
    ReadingIn,
    ReadingOut,
    TankOut,
)

router = APIRouter()


@router.post(
    "/readings",
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"model": ReadingOut, "description": "Already ingested: the first stored reading"},
        422: {"model": ErrorResponse},
    },
)
async def ingest_reading(
    body: ReadingIn, response: Response, use_case: IngestReadingDep
) -> ReadingOut:
    """Ingest one sensor reading.

    Responds 201 with the created reading. Idempotent: re-sending a reading with the same
    tank, sensor, measurement and `recorded_at` responds 200 with the STORED (first)
    reading, whatever value the repeated request carried.
    """
    result = await use_case.execute(IngestReadingCommand(**body.model_dump()))
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return ReadingOut.from_domain(result.reading)


@router.get("/tanks")
async def list_tanks(use_case: ListTanksDep) -> list[TankOut]:
    """List every registered tank, sorted by id, with its latest reading per measurement."""
    return [TankOut.from_domain(overview) for overview in await use_case.execute()]


@router.get(
    "/tanks/{tank_id}",
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def get_tank(tank_id: str, use_case: GetTankDep) -> TankOut:
    """One tank with its latest reading per measurement; 404 if it was never registered."""
    return TankOut.from_domain(await use_case.execute(tank_id))


@router.get(
    "/tanks/{tank_id}/readings",
    responses={422: {"model": ErrorResponse}},
)
async def list_readings(
    tank_id: str,
    start: Annotated[AwareDatetime, Query()],
    end: Annotated[AwareDatetime, Query()],
    use_case: ListReadingsDep,
) -> list[ReadingOut]:
    """List a tank's readings in the half-open range [start, end), oldest first."""
    readings = await use_case.execute(tank_id, start, end)
    return [ReadingOut.from_domain(r) for r in readings]


@router.get(
    "/tanks/{tank_id}/readings/aggregated",
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def list_aggregated_readings(
    tank_id: str,
    bucket: Annotated[AggregationBucket, Query()],
    start: Annotated[AwareDatetime, Query()],
    end: Annotated[AwareDatetime, Query()],
    use_case: ListAggregatedReadingsDep,
    measurement: Annotated[list[MeasurementType] | None, Query()] = None,
) -> AggregatedReadingsOut:
    """Per-bucket avg/min/max/count, grouped by measurement, for buckets starting in [start, end).

    `measurement` may be repeated to select series; all of them by default. All sensors of a
    measurement are aggregated together. Points are ascending; the newest bucket may be partial.
    """
    points = await use_case.execute(tank_id, bucket, start, end, measurement)
    return AggregatedReadingsOut.from_domain(
        normalize_id("tank_id", tank_id),
        bucket,
        list(dict.fromkeys(measurement)) if measurement else list(MeasurementType),
        points,
    )


@router.get("/batch-templates")
async def list_batch_templates() -> list[BatchTemplateOut]:
    """The style presets that prefill a batch's target ranges (`custom` has none)."""
    return [
        BatchTemplateOut.from_domain(template, targets)
        for template in StyleTemplate
        if (targets := template_targets(template)) is not None
    ]


@router.post(
    "/batches",
    status_code=status.HTTP_201_CREATED,
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def create_batch(body: BatchIn, use_case: CreateBatchDep) -> BatchOut:
    """Plan a batch in a registered tank.

    The `template` prefills the targets; fields sent in `targets` override it. A `custom`
    template needs `temperature_min`, `temperature_max` and `pressure_max`. `planned_start`
    defaults to now.
    """
    command = CreateBatchCommand(
        tank_id=body.tank_id,
        beer_name=body.beer_name,
        style=body.style,
        template=body.template,
        targets=body.targets.model_dump(exclude_unset=True) if body.targets else None,
        planned_start=body.planned_start,
        expected_end=body.expected_end,
        notes=body.notes,
    )
    return BatchOut.from_domain(await use_case.execute(command))


@router.get("/batches", responses={422: {"model": ErrorResponse}})
async def list_batches(
    use_case: ListBatchesDep,
    tank_id: Annotated[str | None, Query()] = None,
    status: Annotated[BatchStatus | None, Query()] = None,
) -> list[BatchOut]:
    """List batches, newest first, optionally filtered by tank and/or status."""
    return [BatchOut.from_domain(b) for b in await use_case.execute(tank_id, status)]


@router.get(
    "/batches/{batch_id}",
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def get_batch(batch_id: UUID, use_case: GetBatchDep) -> BatchOut:
    """One batch; 404 if unknown."""
    return BatchOut.from_domain(await use_case.execute(batch_id))


@router.patch(
    "/batches/{batch_id}",
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
async def update_batch(batch_id: UUID, body: BatchPatch, use_case: UpdateBatchDep) -> BatchOut:
    """Edit a planned or active batch (409 once finished). Only the fields sent change.

    `version` is optional: if sent and the batch has moved on, responds 409 on `version`.
    """
    changes = body.model_dump(exclude_unset=True)
    expected_version = changes.pop("version", None)
    return BatchOut.from_domain(await use_case.execute(batch_id, changes, expected_version))


@router.post(
    "/batches/{batch_id}/start",
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def start_batch(batch_id: UUID, use_case: StartBatchDep) -> BatchOut:
    """planned -> active. 409 if not planned or if the tank already has an active batch."""
    return BatchOut.from_domain(await use_case.execute(batch_id))


@router.post(
    "/batches/{batch_id}/finish",
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def finish_batch(batch_id: UUID, use_case: FinishBatchDep) -> BatchOut:
    """active -> finished. 409 if the batch is not active."""
    return BatchOut.from_domain(await use_case.execute(batch_id))
