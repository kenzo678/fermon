import logging
from dataclasses import dataclass

from fastapi import Response

SESSION_COOKIE = "fermon_session"

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SessionSettings:
    ttl_seconds: int
    cookie_secure: bool


def set_session_cookie(response: Response, token: str, settings: SessionSettings) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.ttl_seconds,
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
    )


def clear_session_cookie(response: Response, settings: SessionSettings) -> None:
    response.delete_cookie(
        SESSION_COOKIE, path="/", httponly=True, samesite="lax", secure=settings.cookie_secure
    )


def warn_if_cookie_not_secure(settings: SessionSettings) -> None:
    """Startup check: a session cookie without ``Secure`` travels over plain http."""
    if not settings.cookie_secure:
        logger.warning(
            "SESSION_COOKIE_SECURE is false: the session cookie is also sent over plain http. "
            "Set SESSION_COOKIE_SECURE=true when serving the API over https."
        )
