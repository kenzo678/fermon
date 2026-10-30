from typing import Annotated

from fastapi import APIRouter, Query, Response, status
from pydantic import AwareDatetime

from fermon.fermentation.application.ingest_reading import IngestReadingCommand
from fermon.fermentation.domain import AggregationBucket, MeasurementType, normalize_id
from fermon.fermentation.infrastructure.http.dependencies import (
    GetTankDep,
    IngestReadingDep,
    ListAggregatedReadingsDep,
    ListReadingsDep,
    ListTanksDep,
)
from fermon.fermentation.infrastructure.http.schemas import (
    AggregatedReadingsOut,
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
