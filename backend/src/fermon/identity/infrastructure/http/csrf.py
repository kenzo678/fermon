from fastapi import Request

from fermon.identity.domain import MissingCsrfHeaderError

CSRF_HEADER = "X-Requested-With"
CSRF_VALUE = "fermon"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


async def require_csrf_header(request: Request) -> None:
    """Reject state-changing requests that lack ``X-Requested-With: fermon`` (403).

    Browsers cannot add a custom header to a cross-site form or image request, and a cross-site
    ``fetch`` that adds one triggers a CORS preflight that only the allowed origins pass. So the
    header proves the call came from our own page, on top of the ``SameSite=Lax`` cookie.
    """
    if request.method not in _SAFE_METHODS and request.headers.get(CSRF_HEADER) != CSRF_VALUE:
        raise MissingCsrfHeaderError()
