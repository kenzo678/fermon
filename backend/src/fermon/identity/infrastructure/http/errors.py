from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from fermon.identity.domain import (
    ConcurrentUserUpdateError,
    EmailAlreadyUsedError,
    IdentityError,
    InvalidCredentialsError,
    InvalidUserError,
    LastAdminError,
    PermissionDeniedError,
    TooManyLoginAttemptsError,
    UserNotFoundError,
    WeakPasswordError,
)

# error class -> HTTP status (first isinstance match wins, so list subclasses before bases)
_STATUS = {
    InvalidCredentialsError: status.HTTP_401_UNAUTHORIZED,
    PermissionDeniedError: status.HTTP_403_FORBIDDEN,
    TooManyLoginAttemptsError: status.HTTP_429_TOO_MANY_REQUESTS,
    UserNotFoundError: status.HTTP_404_NOT_FOUND,
    EmailAlreadyUsedError: status.HTTP_409_CONFLICT,
    ConcurrentUserUpdateError: status.HTTP_409_CONFLICT,
    LastAdminError: status.HTTP_409_CONFLICT,
    InvalidUserError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    WeakPasswordError: status.HTTP_422_UNPROCESSABLE_CONTENT,
}
# error class -> field of the unified `{"detail": [...]}` shape, for errors without a `field`
_FIELDS = {
    UserNotFoundError: "user_id",
    EmailAlreadyUsedError: "email",
    ConcurrentUserUpdateError: "version",
}


async def identity_error_handler(_: Request, exc: Exception) -> JSONResponse:
    field = getattr(exc, "field", None) or next(
        (f for cls, f in _FIELDS.items() if isinstance(exc, cls)), None
    )
    status_code = next(
        (code for cls, code in _STATUS.items() if isinstance(exc, cls)),
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
    headers = (
        {"Retry-After": str(exc.retry_after_seconds)}
        if isinstance(exc, TooManyLoginAttemptsError)
        else None
    )
    return JSONResponse(
        status_code=status_code,
        content={"detail": [{"field": field, "message": str(exc)}]},
        headers=headers,
    )


def register_identity_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(IdentityError, identity_error_handler)
