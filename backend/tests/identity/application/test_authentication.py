from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from fermon.identity.application import (
    ChangeOwnPassword,
    CurrentUser,
    Login,
    LoginThrottle,
    Logout,
)
from fermon.identity.domain import (
    InactiveUserError,
    InvalidCredentialsError,
    Role,
    Session,
    TooManyLoginAttemptsError,
    User,
    WeakPasswordError,
    hash_token,
)
from tests.identity.fakes import (
    FakePasswordHasher,
    InMemoryCredentialStore,
    InMemorySessionStore,
    InMemoryUserRepository,
)

T0 = datetime(2026, 1, 1, 12, tzinfo=UTC)
TTL = timedelta(hours=8)


class Env:
    def __init__(self) -> None:
        self.now = T0
        self.users = InMemoryUserRepository()
        self.sessions = InMemorySessionStore()
        self.hasher = FakePasswordHasher()
        self.tokens = iter(f"token-{n}" for n in range(1, 100))
        clock = lambda: self.now  # noqa: E731
        self.throttle = LoginThrottle(clock, window=timedelta(minutes=15))
        self.credentials = InMemoryCredentialStore(self.users, self.sessions)
        self.login = Login(
            self.users,
            self.sessions,
            self.hasher,
            clock,
            TTL,
            self.throttle,
            new_token=lambda: next(self.tokens),
        )
        self.logout = Logout(self.sessions, clock)
        self.current = CurrentUser(self.users, self.sessions, clock)
        self.change = ChangeOwnPassword(self.hasher, clock, self.credentials)

    async def add_user(self, n: int = 1, **overrides: object) -> User:
        values: dict[str, object] = {
            "id": UUID(int=n),
            "email": f"user{n}@example.com",
            "display_name": f"User {n}",
            "role": Role.BREWER,
            "password_hash": await self.hasher.hash("correct-password"),
            "created_at": T0,
        }
        user = User(**{**values, **overrides})  # type: ignore[arg-type]
        await self.users.add(user)
        return user


@pytest.fixture
def env() -> Env:
    return Env()


async def test_login_returns_the_user_and_stores_only_the_token_hash(env: Env) -> None:
    user = await env.add_user()

    logged_in, token = await env.login.execute("User1@Example.com ", "correct-password")

    assert logged_in == user and token == "token-1"
    assert list(env.sessions.sessions) == [hash_token("token-1")]
    stored = env.sessions.sessions[hash_token("token-1")]
    assert (stored.user_id, stored.created_at, stored.expires_at) == (user.id, T0, T0 + TTL)


async def test_wrong_password_unknown_email_and_inactive_user_fail_identically(env: Env) -> None:
    await env.add_user(1)
    await env.add_user(2, active=False)
    messages = set()
    for email, password in [
        ("user1@example.com", "wrong-password"),
        ("nobody@example.com", "correct-password"),
        ("user2@example.com", "correct-password"),
        ("not-an-email", "correct-password"),
    ]:
        with pytest.raises(InvalidCredentialsError) as error:
            await env.login.execute(email, password, "1.1.1.1")
        messages.add(str(error.value))
    assert len(messages) == 1
    assert env.sessions.sessions == {}


async def test_unknown_email_still_spends_the_time_of_a_password_check(env: Env) -> None:
    with pytest.raises(InvalidCredentialsError):
        await env.login.execute("nobody@example.com", "whatever-password")
    assert env.hasher.dummy_verifications == 1


async def test_current_user_resolves_a_valid_token(env: Env) -> None:
    user = await env.add_user()
    _, token = await env.login.execute(user.email, "correct-password")
    assert await env.current.execute(token) == user


@pytest.mark.parametrize("token", [None, "", "unknown-token"])
async def test_current_user_rejects_missing_or_unknown_tokens(env: Env, token: str | None) -> None:
    with pytest.raises(InvalidCredentialsError):
        await env.current.execute(token)


async def test_session_expires_after_the_ttl(env: Env) -> None:
    user = await env.add_user()
    _, token = await env.login.execute(user.email, "correct-password")
    env.now = T0 + TTL - timedelta(seconds=1)
    assert await env.current.execute(token) == user
    env.now = T0 + TTL
    with pytest.raises(InvalidCredentialsError):
        await env.current.execute(token)


async def test_logout_revokes_the_session_and_is_idempotent(env: Env) -> None:
    user = await env.add_user()
    _, token = await env.login.execute(user.email, "correct-password")
    await env.logout.execute(token)
    await env.logout.execute(token)
    await env.logout.execute(None)
    await env.logout.execute("unknown-token")
    with pytest.raises(InvalidCredentialsError):
        await env.current.execute(token)


async def test_deactivated_user_loses_access_with_a_live_session(env: Env) -> None:
    user = await env.add_user()
    _, token = await env.login.execute(user.email, "correct-password")
    env.users.users[user.id] = user.changed(active=False)
    with pytest.raises(InvalidCredentialsError):
        await env.current.execute(token)


async def test_change_password_clears_the_flag_and_revokes_other_sessions(env: Env) -> None:
    user = await env.add_user(must_change_password=True)
    _, mine = await env.login.execute(user.email, "correct-password")
    _, other = await env.login.execute(user.email, "correct-password")

    updated = await env.change.execute(user, mine, "correct-password", "a-brand-new-password")

    assert not updated.must_change_password and updated.version == user.version + 1
    assert await env.hasher.verify(updated.password_hash, "a-brand-new-password")
    assert (await env.current.execute(mine)).id == user.id
    with pytest.raises(InvalidCredentialsError):
        await env.current.execute(other)
    await env.login.execute(user.email, "a-brand-new-password")


async def test_change_password_checks_the_current_password_and_the_policy(env: Env) -> None:
    user = await env.add_user()
    _, token = await env.login.execute(user.email, "correct-password")
    with pytest.raises(InvalidCredentialsError):
        await env.change.execute(user, token, "wrong-password", "a-brand-new-password")
    with pytest.raises(WeakPasswordError) as weak:
        await env.change.execute(user, token, "correct-password", "short")
    assert weak.value.field == "new_password"
    with pytest.raises(WeakPasswordError):
        await env.change.execute(user, token, "correct-password", "correct-password")


async def test_the_sixth_failed_login_for_an_account_is_throttled_even_with_the_right_password(
    env: Env,
) -> None:
    user = await env.add_user()
    for _ in range(5):
        with pytest.raises(InvalidCredentialsError):
            await env.login.execute(user.email, "wrong-password", "1.1.1.1")
    verifications = env.hasher.verifications

    with pytest.raises(TooManyLoginAttemptsError):
        await env.login.execute(user.email, "correct-password", "2.2.2.2")

    assert env.hasher.verifications == verifications  # rejected before any password work
    env.now = T0 + timedelta(minutes=15)
    await env.login.execute(user.email, "correct-password", "2.2.2.2")


async def test_a_successful_login_resets_the_failures_of_the_account(env: Env) -> None:
    user = await env.add_user()
    for _ in range(4):
        with pytest.raises(InvalidCredentialsError):
            await env.login.execute(user.email, "wrong-password", "1.1.1.1")
    await env.login.execute(user.email, "correct-password", "1.1.1.1")
    for _ in range(4):
        with pytest.raises(InvalidCredentialsError):
            await env.login.execute(user.email, "wrong-password", "1.1.1.1")


async def test_unknown_emails_and_inactive_users_count_as_failures_too(env: Env) -> None:
    await env.add_user(2, active=False)
    for email in ("nobody@example.com", "user2@example.com"):
        for _ in range(5):
            with pytest.raises(InvalidCredentialsError):
                await env.login.execute(email, "correct-password", "1.1.1.1")
        with pytest.raises(TooManyLoginAttemptsError):
            await env.login.execute(email, "correct-password", "1.1.1.1")


async def test_login_purges_expired_sessions_and_keeps_live_ones(env: Env) -> None:
    user = await env.add_user()
    await env.sessions.add(Session(hash_token("old"), user.id, T0 - 2 * TTL, T0 - TTL))
    await env.sessions.add(Session(hash_token("live"), user.id, T0, T0 + TTL))

    await env.login.execute(user.email, "correct-password", "1.1.1.1")

    assert set(env.sessions.sessions) == {hash_token("live"), hash_token("token-1")}


async def test_a_session_whose_user_no_longer_exists_is_invalid_not_inactive(env: Env) -> None:
    user = await env.add_user()
    _, token = await env.login.execute(user.email, "correct-password")
    del env.users.users[user.id]
    with pytest.raises(InvalidCredentialsError) as error:
        await env.current.execute(token)
    assert not isinstance(error.value, InactiveUserError)


async def test_a_failed_revocation_leaves_the_changed_password_untouched(env: Env) -> None:
    user = await env.add_user()
    _, token = await env.login.execute(user.email, "correct-password")
    env.credentials.fail = True
    with pytest.raises(RuntimeError):
        await env.change.execute(user, token, "correct-password", "a-brand-new-password")
    assert env.users.users[user.id] == user
