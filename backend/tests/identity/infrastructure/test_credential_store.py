from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from fermon.identity.domain import ConcurrentUserUpdateError, Role, Session, User, hash_token
from fermon.identity.infrastructure.persistence import (
    SqlAlchemyCredentialStore,
    SqlAlchemySessionStore,
    SqlAlchemyUserRepository,
)
from fermon.identity.infrastructure.persistence import credential_store as credential_module

pytestmark = pytest.mark.integration

T0 = datetime(2026, 1, 1, 12, tzinfo=UTC)


def make_user() -> User:
    return User(
        id=UUID(int=1),
        email="user1@example.com",
        display_name="User 1",
        role=Role.VIEWER,
        password_hash="old-hash",
        created_at=T0,
    )


@pytest.fixture
def credential_store(identity_engine: AsyncEngine) -> SqlAlchemyCredentialStore:
    return SqlAlchemyCredentialStore(async_sessionmaker(identity_engine, expire_on_commit=False))


async def seed(
    user_repository: SqlAlchemyUserRepository, session_store: SqlAlchemySessionStore
) -> User:
    user = make_user()
    await user_repository.add(user)
    for token in ("keep", "drop"):
        await session_store.add(Session(hash_token(token), user.id, T0, T0 + timedelta(hours=8)))
    return user


async def test_password_and_session_revocation_are_written_together(
    credential_store: SqlAlchemyCredentialStore,
    user_repository: SqlAlchemyUserRepository,
    session_store: SqlAlchemySessionStore,
) -> None:
    user = await seed(user_repository, session_store)
    updated = user.changed(password_hash="new-hash", must_change_password=True)

    await credential_store.replace_user_and_revoke_sessions(
        updated, T0, except_token_hash=hash_token("keep")
    )

    assert await user_repository.get(user.id) == updated
    assert (await session_store.get(hash_token("keep"))).revoked_at is None  # type: ignore[union-attr]
    assert (await session_store.get(hash_token("drop"))).revoked_at == T0  # type: ignore[union-attr]


async def test_a_failure_while_revoking_rolls_back_the_new_password(
    credential_store: SqlAlchemyCredentialStore,
    user_repository: SqlAlchemyUserRepository,
    session_store: SqlAlchemySessionStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await seed(user_repository, session_store)

    def boom(*_: object, **__: object) -> None:
        raise RuntimeError("revocation failed")

    monkeypatch.setattr(credential_module, "revocation_statement", boom)

    with pytest.raises(RuntimeError):
        await credential_store.replace_user_and_revoke_sessions(
            user.changed(password_hash="new-hash"), T0
        )

    assert await user_repository.get(user.id) == user
    assert (await session_store.get(hash_token("drop"))).revoked_at is None  # type: ignore[union-attr]


async def test_a_stale_version_writes_nothing(
    credential_store: SqlAlchemyCredentialStore,
    user_repository: SqlAlchemyUserRepository,
    session_store: SqlAlchemySessionStore,
) -> None:
    user = await seed(user_repository, session_store)
    stale = user.changed(password_hash="x").changed(password_hash="y")
    with pytest.raises(ConcurrentUserUpdateError):
        await credential_store.replace_user_and_revoke_sessions(stale, T0)
    assert (await session_store.get(hash_token("drop"))).revoked_at is None  # type: ignore[union-attr]


async def test_purge_expired_deletes_only_expired_sessions(
    user_repository: SqlAlchemyUserRepository, session_store: SqlAlchemySessionStore
) -> None:
    user = make_user()
    await user_repository.add(user)
    await session_store.add(Session(hash_token("old"), user.id, T0, T0 + timedelta(hours=1)))
    await session_store.add(Session(hash_token("live"), user.id, T0, T0 + timedelta(hours=9)))

    await session_store.purge_expired(T0 + timedelta(hours=2))

    assert await session_store.get(hash_token("old")) is None
    assert await session_store.get(hash_token("live")) is not None
