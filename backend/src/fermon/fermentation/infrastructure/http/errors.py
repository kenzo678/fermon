from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from fermon.fermentation.domain import (
    ActiveBatchConflictError,
    BatchNotFoundError,
    ConcurrentBatchUpdateError,
    DomainError,
    InvalidBatchError,
    InvalidBatchTransitionError,
    InvalidIdentifierError,
    InvalidReadingError,
    InvalidTankError,
    TankNotFoundError,
)

_LOCATION_KINDS = {"body", "query", "path"}


def _unprocessable(errors: list[dict[str, str | None]]) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, content={"detail": errors}
    )


async def domain_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """Map domain rule violations to 422 with `{"detail": [{"field", "message"}]}`."""
    field = (
        exc.field
        if isinstance(
            exc, InvalidReadingError | InvalidIdentifierError | InvalidTankError | InvalidBatchError
        )
        else None
    )
    return _unprocessable([{"field": field, "message": str(exc)}])


async def tank_not_found_handler(_: Request, exc: Exception) -> JSONResponse:
    """Map an unknown tank to 404 with the same `{"detail": [{"field", "message"}]}` shape."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": [{"field": "tank_id", "message": str(exc)}]},
    )


async def batch_not_found_handler(_: Request, exc: Exception) -> JSONResponse:
    """Map an unknown batch to 404 with the unified error shape."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": [{"field": "batch_id", "message": str(exc)}]},
    )


async def conflict_handler(_: Request, exc: Exception) -> JSONResponse:
    """Map batch state conflicts (second active batch, forbidden transition) to 409."""
    field = (
        "tank_id"
        if isinstance(exc, ActiveBatchConflictError)
        else "version"
        if isinstance(exc, ConcurrentBatchUpdateError)
        else "status"
    )
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": [{"field": field, "message": str(exc)}]},
    )


async def validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """Map Pydantic request errors to the same 422 shape as domain errors."""
    assert isinstance(exc, RequestValidationError)
    errors: list[dict[str, str | None]] = []
    for error in exc.errors():
        loc = [str(part) for part in error["loc"]]
        if loc and loc[0] in _LOCATION_KINDS:
            loc = loc[1:]
        # A malformed JSON body locates the error by character offset, not by field.
        field = None if error["type"] == "json_invalid" else ".".join(loc) or None
        errors.append({"field": field, "message": str(error["msg"])})
    return _unprocessable(errors)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, domain_error_handler)
    app.add_exception_handler(TankNotFoundError, tank_not_found_handler)
    app.add_exception_handler(BatchNotFoundError, batch_not_found_handler)
    app.add_exception_handler(ActiveBatchConflictError, conflict_handler)
    app.add_exception_handler(InvalidBatchTransitionError, conflict_handler)
    app.add_exception_handler(ConcurrentBatchUpdateError, conflict_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
