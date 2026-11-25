from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from functools import cache
from typing import Annotated

from fastapi import Depends
from fastapi.requests import HTTPConnection
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fermon.identity.application import (
    ChangeOwnPassword,
    Clock,
    CreateUser,
    CredentialStore,
    CurrentUser,
    ListUsers,
    Login,
    LoginThrottle,
    Logout,
    PasswordHasher,
    ResetUserPassword,
    SessionStore,
    UpdateUser,
    UserRepository,
)
from fermon.identity.domain import (
    InvalidCredentialsError,
    PasswordChangeRequiredError,
    PermissionDeniedError,
    Role,
    User,
    can_manage_users,
)
from fermon.identity.infrastructure.hashing import Argon2PasswordHasher
from fermon.identity.infrastructure.http.session_cookie import SESSION_COOKIE, SessionSettings
from fermon.identity.infrastructure.persistence import (
    SqlAlchemyCredentialStore,
    SqlAlchemySessionStore,
    SqlAlchemyUserRepository,
)


def get_session_factory(connection: HTTPConnection) -> async_sessionmaker[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = connection.app.state.session_factory
    return factory


def get_session_settings(connection: HTTPConnection) -> SessionSettings:
    settings: SessionSettings = connection.app.state.session_settings
    return settings


@cache
def _argon2() -> Argon2PasswordHasher:
    return Argon2PasswordHasher()  # one instance: it caches the dummy hash used for timing


def get_password_hasher() -> PasswordHasher:
    return _argon2()


def get_clock() -> Clock:
    return lambda: datetime.now(UTC)


SessionFactory = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]
SessionSettingsDep = Annotated[SessionSettings, Depends(get_session_settings)]
HasherDep = Annotated[PasswordHasher, Depends(get_password_hasher)]
ClockDep = Annotated[Clock, Depends(get_clock)]


def get_user_repository(session_factory: SessionFactory) -> UserRepository:
    return SqlAlchemyUserRepository(session_factory)


def get_session_store(session_factory: SessionFactory) -> SessionStore:
    return SqlAlchemySessionStore(session_factory)


def get_credential_store(session_factory: SessionFactory) -> CredentialStore:
    return SqlAlchemyCredentialStore(session_factory)


def get_login_throttle(connection: HTTPConnection) -> LoginThrottle:
    throttle: LoginThrottle = connection.app.state.login_throttle
    return throttle


def get_client_ip(connection: HTTPConnection) -> str | None:
    """The peer address; ``X-Forwarded-For`` is deliberately ignored (a client can forge it)."""
    return connection.client.host if connection.client else None


CredentialsDep = Annotated[CredentialStore, Depends(get_credential_store)]
LoginThrottleDep = Annotated[LoginThrottle, Depends(get_login_throttle)]
ClientIpDep = Annotated[str | None, Depends(get_client_ip)]
UsersDep = Annotated[UserRepository, Depends(get_user_repository)]
SessionsDep = Annotated[SessionStore, Depends(get_session_store)]


def get_login(
    users: UsersDep,
    sessions: SessionsDep,
    hasher: HasherDep,
    clock: ClockDep,
    settings: SessionSettingsDep,
    throttle: LoginThrottleDep,
) -> Login:
    return Login(users, sessions, hasher, clock, timedelta(seconds=settings.ttl_seconds), throttle)


def get_logout(sessions: SessionsDep, clock: ClockDep) -> Logout:
    return Logout(sessions, clock)


def get_current_user_use_case(
    users: UsersDep, sessions: SessionsDep, clock: ClockDep
) -> CurrentUser:
    return CurrentUser(users, sessions, clock)


def get_change_own_password(
    hasher: HasherDep, clock: ClockDep, credentials: CredentialsDep
) -> ChangeOwnPassword:
    return ChangeOwnPassword(hasher, clock, credentials)


def get_create_user(users: UsersDep, hasher: HasherDep, clock: ClockDep) -> CreateUser:
    return CreateUser(users, hasher, clock)


def get_list_users(users: UsersDep) -> ListUsers:
    return ListUsers(users)


def get_update_user(users: UsersDep, sessions: SessionsDep, clock: ClockDep) -> UpdateUser:
    return UpdateUser(users, sessions, clock)


def get_reset_user_password(
    users: UsersDep, hasher: HasherDep, clock: ClockDep, credentials: CredentialsDep
) -> ResetUserPassword:
    return ResetUserPassword(users, hasher, clock, credentials)


def get_session_token(connection: HTTPConnection) -> str | None:
    """The raw session token from the cookie (works for HTTP and WebSocket connections)."""
    return connection.cookies.get(SESSION_COOKIE)


SessionTokenDep = Annotated[str | None, Depends(get_session_token)]


async def get_current_user_allow_password_change(
    token: SessionTokenDep,
    current_user: Annotated[CurrentUser, Depends(get_current_user_use_case)],
) -> User:
    """The signed-in user (401 otherwise), even while a temporary password is still set.

    Only for the endpoints a user in that state must reach: ``/auth/me``, ``/auth/password``.
    Everything else uses ``get_current_user``.
    """
    return await current_user.execute(token)


async def get_current_user(
    user: Annotated[User, Depends(get_current_user_allow_password_change)],
) -> User:
    """The signed-in user, or 401; 403 while the account still has a temporary password.

    Apply it (directly or through ``require_permission``) to every route and WebSocket that
    needs a session, so the forced password change cannot be skipped.
    """
    if user.must_change_password:
        raise PasswordChangeRequiredError()
    return user


async def get_websocket_user(
    token: SessionTokenDep,
    current_user: Annotated[CurrentUser, Depends(get_current_user_use_case)],
) -> User | None:
    """The signed-in user of a WebSocket handshake, or ``None``.

    Exceptions raised by a dependency cannot become an HTTP error once the handshake is a
    WebSocket, so the endpoint closes with 4401 itself when this returns ``None`` (no valid
    session, or the account still has a temporary password).
    """
    try:
        user = await current_user.execute(token)
    except InvalidCredentialsError:
        return None
    return None if user.must_change_password else user


CurrentUserDep = Annotated[User, Depends(get_current_user)]
CurrentUserAllowingPasswordChangeDep = Annotated[
    User, Depends(get_current_user_allow_password_change)
]


def require_permission(check: Callable[[Role], bool]) -> Callable[[User], Awaitable[User]]:
    """Dependency factory: 401 without a session, 403 unless ``check(role)`` allows the role.

    ``check`` is one of the helpers in ``fermon.identity.domain`` (``can_write_batches``...).
    """

    async def dependency(user: CurrentUserDep) -> User:
        if not check(user.role):
            raise PermissionDeniedError()
        return user

    return dependency


WebSocketUserDep = Annotated[User | None, Depends(get_websocket_user)]
AdminUserDep = Annotated[User, Depends(require_permission(can_manage_users))]
LoginDep = Annotated[Login, Depends(get_login)]
LogoutDep = Annotated[Logout, Depends(get_logout)]
ChangeOwnPasswordDep = Annotated[ChangeOwnPassword, Depends(get_change_own_password)]
CreateUserDep = Annotated[CreateUser, Depends(get_create_user)]
ListUsersDep = Annotated[ListUsers, Depends(get_list_users)]
UpdateUserDep = Annotated[UpdateUser, Depends(get_update_user)]
ResetUserPasswordDep = Annotated[ResetUserPassword, Depends(get_reset_user_password)]
