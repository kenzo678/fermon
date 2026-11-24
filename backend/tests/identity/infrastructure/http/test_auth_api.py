from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

import pytest_asyncio
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient, Response

from fermon.identity.application import LoginThrottle
from fermon.identity.domain import Role, User, can_write_batches
from fermon.identity.infrastructure.http.dependencies import (
    CurrentUserDep,
    get_clock,
    get_credential_store,
    get_password_hasher,
    get_session_store,
    get_user_repository,
    require_permission,
)
from fermon.main import create_app
from fermon.shared.config import Settings
from tests.identity.fakes import (
    FakePasswordHasher,
    InMemoryCredentialStore,
    InMemorySessionStore,
    InMemoryUserRepository,
)

T0 = datetime(2026, 1, 1, 12, tzinfo=UTC)
PASSWORD = "correct-password"
Make = Callable[..., AsyncClient]


class World:
    def __init__(self) -> None:
        self.now = T0
        self.users = InMemoryUserRepository()
        self.sessions = InMemorySessionStore()
        self.hasher = FakePasswordHasher()
        self.credentials = InMemoryCredentialStore(self.users, self.sessions)
        self.app: FastAPI = create_app(Settings())
        self.install(self.app)

    def install(self, app: FastAPI) -> None:
        """Point an app at the in-memory fakes and the controllable clock."""
        overrides: Any = app.dependency_overrides
        overrides[get_user_repository] = lambda: self.users
        overrides[get_session_store] = lambda: self.sessions
        overrides[get_credential_store] = lambda: self.credentials
        overrides[get_password_hasher] = lambda: self.hasher
        overrides[get_clock] = lambda: lambda: self.now
        app.state.login_throttle = LoginThrottle(lambda: self.now, window=timedelta(minutes=15))

    async def add(self, n: int, role: Role, **overrides: object) -> User:
        values: dict[str, object] = {
            "id": UUID(int=n),
            "email": f"user{n}@example.com",
            "display_name": f"User {n}",
            "role": role,
            "password_hash": await self.hasher.hash(PASSWORD),
            "created_at": T0 + timedelta(minutes=n),
        }
        user = User(**{**values, **overrides})  # type: ignore[arg-type]
        await self.users.add(user)
        return user


@pytest_asyncio.fixture
async def world() -> World:
    return World()


@pytest_asyncio.fixture
async def client(world: World) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=world.app), base_url="http://test") as c:
        yield c


async def login(client: AsyncClient, user: User) -> dict[str, str]:
    response = await client.post("/auth/login", json={"email": user.email, "password": PASSWORD})
    assert response.status_code == 200
    client.cookies.clear()  # each request carries its own explicit Cookie header
    return {"Cookie": f"fermon_session={_cookie_value(response)}"}


def _cookie_value(response: Response) -> str:
    return response.headers["set-cookie"].split(";")[0].split("=", 1)[1]


def error(field: str | None, message: str) -> dict[str, Any]:
    return {"detail": [{"field": field, "message": message}]}


async def test_login_returns_the_user_without_secrets_and_sets_a_hardened_cookie(
    client: AsyncClient, world: World
) -> None:
    user = await world.add(1, Role.BREWER, must_change_password=True)

    response = await client.post(
        "/auth/login", json={"email": " USER1@example.com", "password": PASSWORD}
    )

    assert response.status_code == 200
    assert response.json() == {
        "user": {
            "id": str(user.id),
            "email": "user1@example.com",
            "display_name": "User 1",
            "role": "brewer",
            "must_change_password": True,
            "active": True,
            "version": 1,
        }
    }
    cookie = response.headers["set-cookie"].lower()
    assert cookie.startswith("fermon_session=")
    for attribute in ("httponly", "samesite=lax", "path=/", f"max-age={8 * 3600}"):
        assert attribute in cookie
    assert "secure" not in cookie.replace("samesite", "")
    assert "password_hash" not in response.text and PASSWORD not in response.text


async def test_cookie_is_marked_secure_when_configured(world: World) -> None:
    world.app = create_app(Settings(session_cookie_secure=True, session_ttl_seconds=60))
    world.install(world.app)
    user = await world.add(1, Role.VIEWER)
    async with AsyncClient(transport=ASGITransport(app=world.app), base_url="http://test") as c:
        response = await c.post("/auth/login", json={"email": user.email, "password": PASSWORD})
    cookie = response.headers["set-cookie"].lower()
    assert "; secure" in cookie and "max-age=60" in cookie


async def test_failed_logins_are_indistinguishable_and_set_no_cookie(
    client: AsyncClient, world: World
) -> None:
    await world.add(1, Role.VIEWER)
    await world.add(2, Role.VIEWER, active=False)
    for email in ("user1@example.com", "nobody@example.com", "user2@example.com"):
        password = "wrong-password" if email == "user1@example.com" else PASSWORD
        response = await client.post("/auth/login", json={"email": email, "password": password})
        assert response.status_code == 401
        assert response.json() == error(None, "invalid email or password")
        assert "set-cookie" not in response.headers


async def test_login_validates_the_body_with_the_unified_shape(client: AsyncClient) -> None:
    response = await client.post("/auth/login", json={"email": "a@b.co"})
    assert response.status_code == 422
    assert response.json()["detail"][0]["field"] == "password"


async def test_me_needs_a_live_session(client: AsyncClient, world: World) -> None:
    user = await world.add(1, Role.VIEWER)
    assert (await client.get("/auth/me")).status_code == 401
    assert (
        await client.get("/auth/me", headers={"Cookie": "fermon_session=bogus"})
    ).status_code == 401

    headers = await login(client, user)
    me = await client.get("/auth/me", headers=headers)
    assert me.status_code == 200 and me.json()["user"]["id"] == str(user.id)

    world.now = T0 + timedelta(hours=8)
    assert (await client.get("/auth/me", headers=headers)).status_code == 401


async def test_logout_revokes_the_session_clears_the_cookie_and_is_idempotent(
    client: AsyncClient, world: World
) -> None:
    headers = await login(client, await world.add(1, Role.VIEWER))

    response = await client.post("/auth/logout", headers=headers)

    assert response.status_code == 204
    cleared = response.headers["set-cookie"].lower()
    assert "fermon_session=" in cleared and "max-age=0" in cleared and "path=/" in cleared
    assert (await client.get("/auth/me", headers=headers)).status_code == 401
    assert (await client.post("/auth/logout")).status_code == 204


async def test_change_password_flow(client: AsyncClient, world: World) -> None:
    user = await world.add(1, Role.BREWER, must_change_password=True)
    headers = await login(client, user)
    other = await login(client, user)

    wrong = await client.post(
        "/auth/password",
        headers=headers,
        json={"current_password": "nope-nope-nope", "new_password": "a-brand-new-password"},
    )
    weak = await client.post(
        "/auth/password",
        headers=headers,
        json={"current_password": PASSWORD, "new_password": "short"},
    )
    ok = await client.post(
        "/auth/password",
        headers=headers,
        json={"current_password": PASSWORD, "new_password": "a-brand-new-password"},
    )

    assert wrong.status_code == 401 and wrong.json() == error(None, "current password is incorrect")
    assert weak.status_code == 422 and weak.json()["detail"][0]["field"] == "new_password"
    assert ok.status_code == 204
    me = await client.get("/auth/me", headers=headers)
    assert me.json()["user"]["must_change_password"] is False
    assert (await client.get("/auth/me", headers=other)).status_code == 401
    assert (await client.post("/auth/password", json={})).status_code == 401


async def test_change_password_without_a_session_is_401(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/password",
        json={"current_password": PASSWORD, "new_password": "a-brand-new-password"},
    )
    assert response.status_code == 401


async def test_users_endpoints_need_a_session_and_the_admin_role(
    client: AsyncClient, world: World
) -> None:
    admin = await world.add(1, Role.ADMIN)
    viewer = await world.add(2, Role.VIEWER)
    brewer = await world.add(3, Role.BREWER)
    target = f"/users/{admin.id}"
    calls = [
        ("GET", "/users", None),
        (
            "POST",
            "/users",
            {
                "email": "n@example.com",
                "display_name": "N",
                "role": "viewer",
                "temporary_password": "temporary-pass",
            },
        ),
        ("PATCH", target, {"version": 1, "active": False}),
        ("POST", f"{target}/reset-password", {"temporary_password": "temporary-pass"}),
    ]
    for who in (viewer, brewer):
        headers = await login(client, who)
        for method, path, body in calls:
            response = await client.request(method, path, json=body, headers=headers)
            assert response.status_code == 403, (who.role, method, path)
            assert response.json() == error(None, "you do not have permission to do this")
    for method, path, body in calls:
        assert (await client.request(method, path, json=body)).status_code == 401
    assert (await client.get("/users", headers=await login(client, admin))).status_code == 200


async def test_admin_lists_and_creates_users(client: AsyncClient, world: World) -> None:
    headers = await login(client, await world.add(1, Role.ADMIN))
    world.now = T0 + timedelta(hours=1)

    created = await client.post(
        "/users",
        headers=headers,
        json={
            "email": "New@Example.com",
            "display_name": "Newbie",
            "role": "viewer",
            "temporary_password": "temporary-pass",
        },
    )

    assert created.status_code == 201
    body = created.json()
    assert (body["email"], body["role"], body["must_change_password"]) == (
        "new@example.com",
        "viewer",
        True,
    )
    assert "password_hash" not in body and "temporary" not in created.text
    listing = await client.get("/users", headers=headers)
    assert [u["email"] for u in listing.json()] == ["user1@example.com", "new@example.com"]
    assert all("password_hash" not in u for u in listing.json())


async def test_create_user_error_shapes(client: AsyncClient, world: World) -> None:
    headers = await login(client, await world.add(1, Role.ADMIN))
    base = {
        "email": "n@example.com",
        "display_name": "N",
        "role": "viewer",
        "temporary_password": "temporary-pass",
    }

    duplicate = await client.post(
        "/users", headers=headers, json={**base, "email": "USER1@example.com"}
    )
    weak = await client.post("/users", headers=headers, json={**base, "temporary_password": "x"})
    bad_role = await client.post("/users", headers=headers, json={**base, "role": "root"})
    bad_email = await client.post("/users", headers=headers, json={**base, "email": "nope"})

    assert duplicate.status_code == 409 and duplicate.json()["detail"][0]["field"] == "email"
    assert weak.status_code == 422 and weak.json()["detail"][0]["field"] == "temporary_password"
    assert bad_role.status_code == 422 and bad_role.json()["detail"][0]["field"] == "role"
    assert bad_email.status_code == 422 and bad_email.json()["detail"][0]["field"] == "email"


async def test_admin_updates_a_user_with_optimistic_versioning(
    client: AsyncClient, world: World
) -> None:
    headers = await login(client, await world.add(1, Role.ADMIN))
    viewer = await world.add(2, Role.VIEWER)

    ok = await client.patch(
        f"/users/{viewer.id}", headers=headers, json={"version": 1, "role": "brewer"}
    )
    stale = await client.patch(
        f"/users/{viewer.id}", headers=headers, json={"version": 1, "active": False}
    )
    missing = await client.patch(
        f"/users/{UUID(int=99)}", headers=headers, json={"version": 1, "active": False}
    )

    assert ok.status_code == 200 and ok.json()["role"] == "brewer" and ok.json()["version"] == 2
    assert stale.status_code == 409 and stale.json()["detail"][0]["field"] == "version"
    assert missing.status_code == 404 and missing.json()["detail"][0]["field"] == "user_id"


async def test_last_admin_cannot_be_deactivated_over_http(
    client: AsyncClient, world: World
) -> None:
    admin = await world.add(1, Role.ADMIN)
    headers = await login(client, admin)
    response = await client.patch(
        f"/users/{admin.id}", headers=headers, json={"version": 1, "active": False}
    )
    assert response.status_code == 409
    assert response.json()["detail"][0]["field"] == "active"
    assert "last active admin" in response.json()["detail"][0]["message"]


async def test_admin_resets_a_password_and_the_user_must_sign_in_again(
    client: AsyncClient, world: World
) -> None:
    headers = await login(client, await world.add(1, Role.ADMIN))
    viewer = await world.add(2, Role.VIEWER)
    viewer_headers = await login(client, viewer)

    reset = await client.post(
        f"/users/{viewer.id}/reset-password",
        headers=headers,
        json={"temporary_password": "another-temporary"},
    )
    weak = await client.post(
        f"/users/{viewer.id}/reset-password", headers=headers, json={"temporary_password": "x"}
    )

    assert reset.status_code == 204 and weak.status_code == 422
    assert (await client.get("/auth/me", headers=viewer_headers)).status_code == 401
    again = await client.post(
        "/auth/login", json={"email": viewer.email, "password": "another-temporary"}
    )
    assert again.json()["user"]["must_change_password"] is True


async def test_require_permission_is_reusable_on_any_route(
    client: AsyncClient, world: World
) -> None:
    writer = Depends(require_permission(can_write_batches))

    @world.app.get("/_probe")
    async def probe(user: Annotated[User, writer]) -> dict[str, str]:
        return {"role": user.role.value}

    brewer = await login(client, await world.add(1, Role.BREWER))
    viewer = await login(client, await world.add(2, Role.VIEWER))
    assert (await client.get("/_probe", headers=brewer)).json() == {"role": "brewer"}
    assert (await client.get("/_probe", headers=viewer)).status_code == 403
    assert (await client.get("/_probe")).status_code == 401


async def test_login_rejects_an_email_longer_than_the_rfc_limit(client: AsyncClient) -> None:
    email = "a" * 245 + "@example.com"  # 257 characters: above 254, below the old 320
    response = await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 422
    assert response.json()["detail"][0]["field"] == "email"


async def test_temporary_password_blocks_every_route_except_me_password_and_logout(
    client: AsyncClient, world: World
) -> None:
    writer = Depends(require_permission(can_write_batches))

    @world.app.get("/_probe")
    async def probe(user: Annotated[User, writer]) -> dict[str, str]:
        return {"role": user.role.value}

    @world.app.get("/_plain")
    async def plain(user: CurrentUserDep) -> dict[str, str]:
        return {"role": user.role.value}

    admin = await world.add(1, Role.ADMIN, must_change_password=True)
    await world.add(2, Role.BREWER, must_change_password=True)
    headers = await login(client, admin)

    for method, path in [("GET", "/_probe"), ("GET", "/_plain"), ("GET", "/users")]:
        blocked = await client.request(method, path, headers=headers)
        assert blocked.status_code == 403, path
        assert blocked.json() == error(
            "password", "you must change your temporary password before continuing"
        )

    assert (await client.get("/auth/me", headers=headers)).status_code == 200
    wrong = await client.post(
        "/auth/password",
        headers=headers,
        json={"current_password": "nope-nope-nope", "new_password": "a-brand-new-password"},
    )
    assert wrong.status_code == 401
    changed = await client.post(
        "/auth/password",
        headers=headers,
        json={"current_password": PASSWORD, "new_password": "a-brand-new-password"},
    )
    assert changed.status_code == 204
    assert (await client.get("/_plain", headers=headers)).status_code == 200
    assert (await client.get("/users", headers=headers)).status_code == 200


async def test_a_user_with_a_temporary_password_can_still_log_out(
    client: AsyncClient, world: World
) -> None:
    headers = await login(client, await world.add(1, Role.VIEWER, must_change_password=True))
    assert (await client.post("/auth/logout", headers=headers)).status_code == 204
    assert (await client.get("/auth/me", headers=headers)).status_code == 401


async def test_repeated_failed_logins_get_429_with_retry_after_until_the_window_passes(
    client: AsyncClient, world: World
) -> None:
    user = await world.add(1, Role.VIEWER)
    for _ in range(5):
        wrong = await client.post(
            "/auth/login", json={"email": user.email, "password": "wrong-password"}
        )
        assert wrong.status_code == 401

    blocked = await client.post("/auth/login", json={"email": user.email, "password": PASSWORD})

    assert blocked.status_code == 429
    assert blocked.headers["retry-after"] == str(15 * 60)
    assert blocked.json() == error(None, "too many failed login attempts; try again later")
    assert "set-cookie" not in blocked.headers
    world.now = T0 + timedelta(minutes=15)
    ok = await client.post("/auth/login", json={"email": user.email, "password": PASSWORD})
    assert ok.status_code == 200


async def test_a_session_whose_user_was_deleted_is_just_unauthenticated(
    client: AsyncClient, world: World
) -> None:
    user = await world.add(1, Role.VIEWER)
    headers = await login(client, user)
    del world.users.users[user.id]
    response = await client.get("/auth/me", headers=headers)
    assert response.status_code == 401
    assert response.json() == error(None, "authentication required")
