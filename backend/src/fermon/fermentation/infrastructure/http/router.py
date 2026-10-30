from typing import Annotated

from fastapi import APIRouter, Query, Response, status
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
