"""The authorization boundary of the whole app: sessions, roles, CSRF header and device key."""

from collections.abc import AsyncIterator, Callable, Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute, APIWebSocketRoute, RouteContext, iter_route_contexts
from httpx import ASGITransport, AsyncClient

from fermon.identity.application import CurrentUser
from fermon.identity.domain import Role
from fermon.identity.infrastructure.http.csrf import require_csrf_header
from fermon.identity.infrastructure.http.dependencies import (
    get_current_user,
    get_current_user_allow_password_change,
    get_current_user_use_case,
    get_websocket_user,
)
from fermon.identity.infrastructure.http.device_key import require_device_key
from fermon.main import create_app
from tests.auth_helpers import ANONYMOUS, CSRF_HEADERS, role_headers, sign_in_fake_sessions
from tests.identity.fakes import InMemorySessionStore, InMemoryUserRepository

# Routes that are public on purpose: health, the login form's endpoint and FastAPI's own docs.
PUBLIC_ROUTES = {
    "/health",
    "/auth/logout",  # idempotent: signing out without a session is a no-op
    "/auth/login",
    "/openapi.json",
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
}
DEVICE_ROUTES = {"/readings"}  # authenticated by an API key, not by a user session
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
SESSION_DEPENDENCIES = {get_current_user, get_current_user_allow_password_change}


def dependency_calls(dependant: Dependant) -> Iterator[Callable[..., Any]]:
    for sub in dependant.dependencies:
        if sub.call is not None:
            yield sub.call
        yield from dependency_calls(sub)


def route_calls(route: RouteContext) -> set[Callable[..., Any]]:
    return set(dependency_calls(route.dependant))


def api_routes(app: FastAPI) -> list[RouteContext]:
    """HTTP routes with the dependencies of their routers (FastAPI resolves includes lazily)."""
    contexts = iter_route_contexts(app.routes)
    return [c for c in contexts if isinstance(c.original_route, APIRoute)]


def websocket_routes(app: FastAPI) -> list[RouteContext]:
    contexts = iter_route_contexts(app.routes)
    return [c for c in contexts if isinstance(c.original_route, APIWebSocketRoute)]


def test_every_route_requires_a_session_unless_it_is_explicitly_public() -> None:
    app = create_app()
    unprotected = [
        route.path
        for route in api_routes(app)
        if route.path not in PUBLIC_ROUTES | DEVICE_ROUTES
        and not (route_calls(route) & SESSION_DEPENDENCIES)
    ]
    assert unprotected == []


def test_every_websocket_requires_a_session() -> None:
    app = create_app()
    sockets = websocket_routes(app)
    assert sockets
    assert [r.path for r in sockets if get_websocket_user not in route_calls(r)] == []


def test_the_device_route_uses_an_api_key_and_no_session() -> None:
    app = create_app()
    (route,) = [r for r in api_routes(app) if r.path in DEVICE_ROUTES]
    calls = route_calls(route)
    assert require_device_key in calls
    assert not calls & SESSION_DEPENDENCIES


def test_every_route_that_changes_state_requires_the_csrf_header_except_the_device_route() -> None:
    app = create_app()
    unprotected = [
        f"{method} {route.path}"
        for route in api_routes(app)
        for method in (route.methods or set()) - SAFE_METHODS
        if route.path not in DEVICE_ROUTES and require_csrf_header not in route_calls(route)
    ]
    assert unprotected == []


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app()  # no database: authorization must reject before any use case runs
    overrides: Any = app.dependency_overrides
    overrides[get_current_user_use_case] = lambda: CurrentUser(
        InMemoryUserRepository(), InMemorySessionStore(), lambda: datetime.now(UTC)
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def protected_requests() -> list[tuple[str, str]]:
    app = create_app()
    return [
        (method, (route.path or "").replace("{", "").replace("}", ""))
        for route in api_routes(app)
        if route.path not in PUBLIC_ROUTES | DEVICE_ROUTES
        for method in sorted((route.methods or set()) - {"HEAD", "OPTIONS"})
        if not route.path.startswith("/auth/")
    ]


@pytest.mark.parametrize(("method", "path"), protected_requests())
async def test_every_protected_route_answers_401_without_a_session(
    client: AsyncClient, method: str, path: str
) -> None:
    response = await client.request(method, path, headers=CSRF_HEADERS)

    assert response.status_code == 401, response.text
    assert response.json() == {"detail": [{"field": None, "message": "authentication required"}]}


# Writes that need admin or brewer. (evaluate is a POST that only reads: any role.)
WRITES = [
    ("POST", "/batches"),
    ("PATCH", "/batches/x"),
    ("POST", "/batches/x/start"),
    ("POST", "/batches/x/finish"),
    ("POST", "/alerts/x/acknowledge"),
    ("POST", "/quality-profiles"),
    ("PUT", "/quality-profiles/x/specs/bright_beer/ph"),
    ("DELETE", "/quality-profiles/x/specs/bright_beer/ph"),
    ("POST", "/batches/x/lab-analyses"),
]


@pytest.fixture
def role_app() -> FastAPI:
    return sign_in_fake_sessions(create_app())


@pytest.mark.parametrize(("method", "path"), WRITES)
async def test_a_viewer_cannot_write(role_app: FastAPI, method: str, path: str) -> None:
    async with AsyncClient(transport=ASGITransport(app=role_app), base_url="http://test") as c:
        response = await c.request(
            method, path, headers={**CSRF_HEADERS, **role_headers(Role.VIEWER)}
        )

    assert response.status_code == 403, response.text
    assert response.json() == {
        "detail": [{"field": None, "message": "you do not have permission to do this"}]
    }


@pytest.mark.parametrize(("method", "path"), WRITES)
async def test_an_anonymous_caller_cannot_write(role_app: FastAPI, method: str, path: str) -> None:
    async with AsyncClient(transport=ASGITransport(app=role_app), base_url="http://test") as c:
        response = await c.request(
            method, path, headers={**CSRF_HEADERS, **role_headers(ANONYMOUS)}
        )

    assert response.status_code == 401, response.text


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/batches"),
        ("POST", "/auth/logout"),
        ("PUT", "/quality-profiles/x/specs/bright_beer/ph"),
        ("POST", "/users"),
    ],
)
async def test_unsafe_methods_without_the_csrf_header_get_403(
    client: AsyncClient, method: str, path: str
) -> None:
    response = await client.request(method, path)

    assert response.status_code == 403
    assert response.json() == {
        "detail": [
            {
                "field": "X-Requested-With",
                "message": "missing or invalid X-Requested-With header (expected 'fermon')",
            }
        ]
    }


async def test_a_wrong_csrf_header_value_is_rejected(client: AsyncClient) -> None:
    response = await client.post("/auth/logout", headers={"X-Requested-With": "XMLHttpRequest"})

    assert response.status_code == 403


async def test_login_and_password_change_require_the_csrf_header(client: AsyncClient) -> None:
    for path in ("/auth/login", "/auth/password"):
        response = await client.post(path, json={})
        assert response.status_code == 403, path


async def test_safe_methods_do_not_need_the_csrf_header(client: AsyncClient) -> None:
    assert (await client.get("/health")).status_code == 200
    assert (await client.get("/tanks")).status_code == 401  # reached the session check
