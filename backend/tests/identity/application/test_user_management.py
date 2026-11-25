from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from fermon.identity.application import (
    BootstrapAdmin,
    CreateUser,
    CurrentUser,
    ListUsers,
    Login,
    LoginThrottle,
    ResetUserPassword,
    UpdateUser,
)
from fermon.identity.domain import (
    ConcurrentUserUpdateError,
    EmailAlreadyUsedError,
    InvalidCredentialsError,
    LastAdminError,
    PermissionDeniedError,
    Role,
    User,
    UserNotFoundError,
    WeakPasswordError,
)
from tests.identity.fakes import (
    FakePasswordHasher,
    InMemoryCredentialStore,
    InMemorySessionStore,
    InMemoryUserRepository,
)

T0 = datetime(2026, 1, 1, 12, tzinfo=UTC)


class Env:
    def __init__(self) -> None:
        self.users = InMemoryUserRepository()
        self.sessions = InMemorySessionStore()
        self.hasher = FakePasswordHasher()
        clock = lambda: T0  # noqa: E731
        ids = iter(UUID(int=n) for n in range(100, 200))
        self.create = CreateUser(self.users, self.hasher, clock, new_id=lambda: next(ids))
        self.list = ListUsers(self.users)
        self.update = UpdateUser(self.users, self.sessions, clock)
        self.credentials = InMemoryCredentialStore(self.users, self.sessions)
        self.reset = ResetUserPassword(self.users, self.hasher, clock, self.credentials)
        throttle = LoginThrottle(clock, window=timedelta(minutes=15))
        self.login = Login(
            self.users, self.sessions, self.hasher, clock, timedelta(hours=8), throttle
        )
        self.current = CurrentUser(self.users, self.sessions, clock)
        self.bootstrap = BootstrapAdmin(self.users, self.hasher, clock, new_id=lambda: UUID(int=1))

    async def add_user(self, n: int, role: Role, **overrides: object) -> User:
        values: dict[str, object] = {
            "id": UUID(int=n),
            "email": f"user{n}@example.com",
            "display_name": f"User {n}",
            "role": role,
            "password_hash": await self.hasher.hash("correct-password"),
            "created_at": T0 + timedelta(minutes=n),
        }
        user = User(**{**values, **overrides})  # type: ignore[arg-type]
        await self.users.add(user)
        return user


@pytest.fixture
def env() -> Env:
    return Env()


async def test_admin_creates_a_user_who_must_change_the_temporary_password(env: Env) -> None:
    admin = await env.add_user(1, Role.ADMIN)

    created = await env.create.execute(
        admin, "New@Example.com", "Newbie", Role.VIEWER, "temporary-pass"
    )

    assert (created.email, created.role, created.active) == ("new@example.com", Role.VIEWER, True)
    assert created.must_change_password
    assert created.password_hash != "temporary-pass"
    assert await env.hasher.verify(created.password_hash, "temporary-pass")


async def test_create_user_rejects_duplicates_and_weak_passwords(env: Env) -> None:
    admin = await env.add_user(1, Role.ADMIN)
    with pytest.raises(EmailAlreadyUsedError):
        await env.create.execute(admin, "USER1@example.com", "Dup", Role.VIEWER, "temporary-pass")
    with pytest.raises(WeakPasswordError) as weak:
        await env.create.execute(admin, "ok@example.com", "Ok", Role.VIEWER, "short")
    assert weak.value.field == "temporary_password"


@pytest.mark.parametrize("role", [Role.BREWER, Role.VIEWER])
async def test_only_admins_can_manage_users(env: Env, role: Role) -> None:
    admin = await env.add_user(1, Role.ADMIN)
    actor = await env.add_user(2, role)
    calls = [
        env.create.execute(actor, "x@example.com", "X", Role.VIEWER, "temporary-pass"),
        env.list.execute(actor),
        env.update.execute(actor, admin.id, admin.version, active=False),
        env.reset.execute(actor, admin.id, "temporary-pass"),
    ]
    for call in calls:
        with pytest.raises(PermissionDeniedError):
            await call


async def test_list_users_orders_by_creation(env: Env) -> None:
    await env.add_user(2, Role.VIEWER)
    admin = await env.add_user(1, Role.ADMIN)
    assert [u.id.int for u in await env.list.execute(admin)] == [1, 2]


async def test_update_changes_the_requested_fields_and_bumps_the_version(env: Env) -> None:
    admin = await env.add_user(1, Role.ADMIN)
    viewer = await env.add_user(2, Role.VIEWER)

    updated = await env.update.execute(
        admin, viewer.id, viewer.version, role=Role.BREWER, display_name=" Chef "
    )

    assert (updated.role, updated.display_name, updated.active, updated.version) == (
        Role.BREWER,
        "Chef",
        True,
        2,
    )
    assert env.users.users[viewer.id] == updated


async def test_update_rejects_unknown_users_and_stale_versions(env: Env) -> None:
    admin = await env.add_user(1, Role.ADMIN)
    viewer = await env.add_user(2, Role.VIEWER)
    with pytest.raises(UserNotFoundError):
        await env.update.execute(admin, UUID(int=99), 1, active=False)
    with pytest.raises(ConcurrentUserUpdateError):
        await env.update.execute(admin, viewer.id, viewer.version + 1, active=False)


async def test_deactivating_a_user_revokes_their_sessions(env: Env) -> None:
    admin = await env.add_user(1, Role.ADMIN)
    viewer = await env.add_user(2, Role.VIEWER)
    _, token = await env.login.execute(viewer.email, "correct-password", None)

    await env.update.execute(admin, viewer.id, viewer.version, active=False)

    with pytest.raises(InvalidCredentialsError):
        await env.current.execute(token)


async def test_the_last_active_admin_cannot_be_demoted_or_deactivated(env: Env) -> None:
    admin = await env.add_user(1, Role.ADMIN)
    with pytest.raises(LastAdminError) as demotion:
        await env.update.execute(admin, admin.id, admin.version, role=Role.BREWER)
    with pytest.raises(LastAdminError) as deactivation:
        await env.update.execute(admin, admin.id, admin.version, active=False)
    assert demotion.value.field == "role"
    assert deactivation.value.field == "active"
    assert env.users.users[admin.id] == admin


async def test_an_admin_can_step_down_when_another_active_admin_exists(env: Env) -> None:
    first = await env.add_user(1, Role.ADMIN)
    await env.add_user(2, Role.ADMIN)
    updated = await env.update.execute(first, first.id, first.version, role=Role.VIEWER)
    assert updated.role is Role.VIEWER


async def test_an_inactive_admin_does_not_count_as_a_spare_admin(env: Env) -> None:
    first = await env.add_user(1, Role.ADMIN)
    await env.add_user(2, Role.ADMIN, active=False)
    with pytest.raises(LastAdminError):
        await env.update.execute(first, first.id, first.version, active=False)


async def test_reset_password_forces_a_change_and_revokes_every_session(env: Env) -> None:
    admin = await env.add_user(1, Role.ADMIN)
    viewer = await env.add_user(2, Role.VIEWER)
    _, token = await env.login.execute(viewer.email, "correct-password", None)

    reset = await env.reset.execute(admin, viewer.id, "another-temporary")

    assert reset.must_change_password and reset.version == viewer.version + 1
    assert await env.hasher.verify(reset.password_hash, "another-temporary")
    with pytest.raises(InvalidCredentialsError):
        await env.current.execute(token)
    with pytest.raises(WeakPasswordError):
        await env.reset.execute(admin, viewer.id, "short")
    with pytest.raises(UserNotFoundError):
        await env.reset.execute(admin, UUID(int=99), "another-temporary")


async def test_bootstrap_creates_an_active_admin_and_refuses_an_existing_email(env: Env) -> None:
    admin = await env.bootstrap.execute("Boss@Example.com", "Boss", "long-enough-password")
    assert (admin.email, admin.role, admin.must_change_password) == (
        "boss@example.com",
        Role.ADMIN,
        False,
    )
    assert await env.hasher.verify(admin.password_hash, "long-enough-password")
    with pytest.raises(EmailAlreadyUsedError):
        await env.bootstrap.execute("boss@example.com", "Boss", "long-enough-password")
    with pytest.raises(WeakPasswordError):
        await env.bootstrap.execute("other@example.com", "Other", "short")


async def test_a_failed_revocation_leaves_the_reset_password_unchanged(env: Env) -> None:
    admin = await env.add_user(1, Role.ADMIN)
    viewer = await env.add_user(2, Role.VIEWER)
    env.credentials.fail = True

    with pytest.raises(RuntimeError):
        await env.reset.execute(admin, viewer.id, "another-temporary")

    assert env.users.users[viewer.id] == viewer
