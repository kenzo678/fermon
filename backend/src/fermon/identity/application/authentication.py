import secrets
from collections.abc import Callable
from datetime import timedelta

from fermon.identity.application.ports import (
    Clock,
    CredentialStore,
    PasswordHasher,
    SessionStore,
    UserRepository,
)
from fermon.identity.application.throttle import LoginThrottle
from fermon.identity.domain import (
    InactiveUserError,
    InvalidCredentialsError,
    InvalidUserError,
    Session,
    User,
    WeakPasswordError,
    hash_token,
    normalize_email,
    validate_password,
)


def _new_token() -> str:
    return secrets.token_urlsafe(32)


class Login:
    def __init__(
        self,
        users: UserRepository,
        sessions: SessionStore,
        hasher: PasswordHasher,
        clock: Clock,
        session_ttl: timedelta,
        throttle: LoginThrottle,
        new_token: Callable[[], str] = _new_token,
    ) -> None:
        self._users = users
        self._sessions = sessions
        self._hasher = hasher
        self._clock = clock
        self._ttl = session_ttl
        self._throttle = throttle
        self._new_token = new_token

    async def execute(
        self, email: str, password: str, client_ip: str | None = None
    ) -> tuple[User, str]:
        """Authenticate and open a session; returns the user and the (only) copy of the token.

        Every failure raises the same ``InvalidCredentialsError`` after a comparable amount of
        work, so the response never reveals whether the email exists or is deactivated. Too many
        recent failures for the account or the address raise ``TooManyLoginAttemptsError``
        before any password work, even when the password is right.
        """
        self._throttle.check(email, client_ip)
        user = await self._find(email)
        if user is None:
            await self._hasher.verify_dummy(password)
            self._throttle.record_failure(email, client_ip)
            raise InvalidCredentialsError()
        if not await self._hasher.verify(user.password_hash, password) or not user.active:
            self._throttle.record_failure(email, client_ip)
            raise InvalidCredentialsError()
        self._throttle.record_success(email)
        now = self._clock()
        await self._sessions.purge_expired(now)
        token = self._new_token()
        await self._sessions.add(
            Session(
                token_hash=hash_token(token),
                user_id=user.id,
                created_at=now,
                expires_at=now + self._ttl,
            )
        )
        return user, token

    async def _find(self, email: str) -> User | None:
        try:
            return await self._users.get_by_email(normalize_email(email))
        except InvalidUserError:
            return None


class Logout:
    def __init__(self, sessions: SessionStore, clock: Clock) -> None:
        self._sessions = sessions
        self._clock = clock

    async def execute(self, token: str | None) -> None:
        if token:
            await self._sessions.revoke(hash_token(token), self._clock())


class CurrentUser:
    def __init__(self, users: UserRepository, sessions: SessionStore, clock: Clock) -> None:
        self._users = users
        self._sessions = sessions
        self._clock = clock

    async def execute(self, token: str | None) -> User:
        """The user owning a live session; ``InvalidCredentialsError`` for anything else."""
        if not token:
            raise InvalidCredentialsError("authentication required")
        session = await self._sessions.get(hash_token(token))
        if session is None or not session.is_valid(self._clock()):
            raise InvalidCredentialsError("authentication required")
        user = await self._users.get(session.user_id)
        if user is None:
            raise InvalidCredentialsError("authentication required")  # the account was deleted
        if not user.active:
            raise InactiveUserError()
        return user


class ChangeOwnPassword:
    def __init__(self, hasher: PasswordHasher, clock: Clock, credentials: CredentialStore) -> None:
        self._hasher = hasher
        self._clock = clock
        self._credentials = credentials

    async def execute(
        self, user: User, token: str, current_password: str, new_password: str
    ) -> User:
        """Set a new password and sign out every other session of the user."""
        if not await self._hasher.verify(user.password_hash, current_password):
            raise InvalidCredentialsError("current password is incorrect")
        validate_password(new_password, "new_password")
        if new_password == current_password:
            raise WeakPasswordError("new_password", "must differ from the current password")
        updated = user.changed(
            password_hash=await self._hasher.hash(new_password), must_change_password=False
        )
        await self._credentials.replace_user_and_revoke_sessions(
            updated, self._clock(), except_token_hash=hash_token(token)
        )
        return updated
