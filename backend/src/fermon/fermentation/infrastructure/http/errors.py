from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from fermon.fermentation.domain import (
    DomainError,
    InvalidIdentifierError,
    InvalidReadingError,
)


async def domain_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """Map domain rule violations to 422, shaped like FastAPI's validation errors."""
    field = exc.field if isinstance(exc, InvalidReadingError | InvalidIdentifierError) else None
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": [{"field": field, "message": str(exc)}]},
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, domain_error_handler)
