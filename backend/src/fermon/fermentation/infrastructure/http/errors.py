from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from fermon.fermentation.domain import (
    DomainError,
    InvalidIdentifierError,
    InvalidReadingError,
)

_LOCATION_KINDS = {"body", "query", "path"}


def _unprocessable(errors: list[dict[str, str | None]]) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, content={"detail": errors}
    )


async def domain_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """Map domain rule violations to 422 with `{"detail": [{"field", "message"}]}`."""
    field = exc.field if isinstance(exc, InvalidReadingError | InvalidIdentifierError) else None
    return _unprocessable([{"field": field, "message": str(exc)}])


async def validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """Map Pydantic request errors to the same 422 shape as domain errors."""
    assert isinstance(exc, RequestValidationError)
    errors: list[dict[str, str | None]] = []
    for error in exc.errors():
        loc = [str(part) for part in error["loc"]]
        if loc and loc[0] in _LOCATION_KINDS:
            loc = loc[1:]
        errors.append({"field": ".".join(loc) or None, "message": str(error["msg"])})
    return _unprocessable(errors)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, domain_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
