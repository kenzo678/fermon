"""Shared test doubles for the authorization layer.

``sign_in_fake_sessions`` makes an app trust a test header instead of the session store, so API
tests exercise the real role checks (``get_current_user``, ``require_permission``) without
logging in: the header ``X-Test-Role`` picks the role (default ``brewer``) and the value
``anonymous`` behaves like a missing session.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import FastAPI, Request

from fermon.identity.domain import InvalidCredentialsError, Role, User
from fermon.identity.infrastructure.http.dependencies import (
    get_current_user_allow_password_change,
    get_websocket_user,
)

T0 = datetime(2026, 1, 1, 12, tzinfo=UTC)

CSRF_HEADERS = {"X-Requested-With": "fermon"}
DEVICE_KEY = "test-device-key"
DEVICE_HEADERS = {"X-Device-Key": DEVICE_KEY}
ROLE_HEADER = "X-Test-Role"
ANONYMOUS = "anonymous"


def role_headers(role: Role | str) -> dict[str, str]:
    return {ROLE_HEADER: role.value if isinstance(role, Role) else role}


def user_with(role: Role, *, must_change_password: bool = False) -> User:
    return User(
        id=UUID(int=900),
        email=f"{role.value}@example.com",
        display_name=role.value.title(),
        role=role,
        password_hash="hashed:unused",
        created_at=T0,
        must_change_password=must_change_password,
    )


def sign_in_fake_sessions(app: FastAPI) -> FastAPI:
    async def fake_user(request: Request) -> User:
        name = request.headers.get(ROLE_HEADER, Role.BREWER.value)
        if name == ANONYMOUS:
            raise InvalidCredentialsError("authentication required")
        return user_with(Role(name))

    async def fake_websocket_user() -> User:
        return user_with(Role.BREWER)

    overrides: Any = app.dependency_overrides
    overrides[get_current_user_allow_password_change] = fake_user
    overrides[get_websocket_user] = fake_websocket_user
    return app
