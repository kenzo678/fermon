from typing import Annotated

from fastapi import APIRouter, Query, status
from pydantic import AwareDatetime

from fermon.fermentation.application.ingest_reading import IngestReadingCommand
from fermon.fermentation.infrastructure.http.dependencies import (
    IngestReadingDep,
    ListReadingsDep,
)
from fermon.fermentation.infrastructure.http.schemas import (
    ErrorResponse,
    ReadingIn,
    ReadingOut,
)

router = APIRouter()


@router.post(
    "/readings",
    status_code=status.HTTP_201_CREATED,
    responses={422: {"model": ErrorResponse}},
)
async def ingest_reading(body: ReadingIn, use_case: IngestReadingDep) -> ReadingOut:
    """Ingest one sensor reading.

    Idempotent: re-sending a reading with the same tank, sensor, measurement and
    `recorded_at` also returns 201 with the reading; the first stored value is kept.
    """
    reading = await use_case.execute(IngestReadingCommand(**body.model_dump()))
    return ReadingOut.from_domain(reading)


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
