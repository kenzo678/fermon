from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from fermon.identity.domain import (
    ConcurrentUserUpdateError,
    EmailAlreadyUsedError,
    Role,
    Session,
    User,
    hash_token,
)
from fermon.identity.infrastructure.persistence import (
    SqlAlchemySessionStore,
    SqlAlchemyUserRepository,
)

pytestmark = pytest.mark.integration

T0 = datetime(2026, 1, 1, 12, tzinfo=UTC)


def make_user(n: int, **overrides: object) -> User:
    values: dict[str, object] = {
        "id": UUID(int=n),
        "email": f"user{n}@example.com",
        "display_name": f"User {n}",
        "role": Role.VIEWER,
        "password_hash": "$argon2id$stub",
        "created_at": T0 + timedelta(minutes=n),
    }
    return User(**{**values, **overrides})  # type: ignore[arg-type]


async def test_add_then_get_by_id_and_by_email_round_trips(
    user_repository: SqlAlchemyUserRepository,
) -> None:
    user = make_user(1, role=Role.BREWER, must_change_password=True)
    await user_repository.add(user)
    assert await user_repository.get(user.id) == user
    assert await user_repository.get_by_email("USER1@example.com") == user
    assert await user_repository.get(UUID(int=99)) is None
    assert await user_repository.get_by_email("nobody@example.com") is None


async def test_email_is_unique_case_insensitively_even_if_the_domain_is_bypassed(
    user_repository: SqlAlchemyUserRepository, identity_engine: object
) -> None:
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.ext.asyncio import AsyncEngine

    await user_repository.add(make_user(1))
    with pytest.raises(EmailAlreadyUsedError):
        await user_repository.add(make_user(2, email="user1@example.com"))
    assert isinstance(identity_engine, AsyncEngine)
    with pytest.raises(IntegrityError, match="uq_users_email_lower"):
        async with identity_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO users (id, email, display_name, role, password_hash, created_at)"
                    " VALUES (gen_random_uuid(), 'USER1@EXAMPLE.COM', 'x', 'viewer', 'h', now())"
                )
            )


async def test_role_is_restricted_by_a_check_constraint(
    user_repository: SqlAlchemyUserRepository, identity_engine: object
) -> None:
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.ext.asyncio import AsyncEngine

    assert isinstance(identity_engine, AsyncEngine)
    with pytest.raises(IntegrityError, match="ck_users_role"):
        async with identity_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO users (id, email, display_name, role, password_hash, created_at)"
                    " VALUES (gen_random_uuid(), 'a@b.co', 'x', 'root', 'h', now())"
                )
            )


async def test_update_requires_the_previous_version(
    user_repository: SqlAlchemyUserRepository,
) -> None:
    user = make_user(1)
    await user_repository.add(user)
    changed = user.changed(role=Role.ADMIN, must_change_password=True)

    await user_repository.update(changed)

    assert await user_repository.get(user.id) == changed
    with pytest.raises(ConcurrentUserUpdateError):
        await user_repository.update(changed)  # stale: the stored version is already 2


async def test_list_orders_by_creation_and_counts_only_active_admins(
    user_repository: SqlAlchemyUserRepository,
) -> None:
    for user in [
        make_user(3, role=Role.ADMIN),
        make_user(1, role=Role.ADMIN, active=False),
        make_user(2, role=Role.BREWER),
    ]:
        await user_repository.add(user)
    assert [u.id.int for u in await user_repository.list()] == [1, 2, 3]
    assert await user_repository.count_active_admins() == 1


async def test_sessions_are_stored_by_hash_and_can_be_revoked(
    user_repository: SqlAlchemyUserRepository, session_store: SqlAlchemySessionStore
) -> None:
    user = make_user(1)
    await user_repository.add(user)
    session = Session(hash_token("t1"), user.id, T0, T0 + timedelta(hours=8))
    await session_store.add(session)

    assert await session_store.get(hash_token("t1")) == session
    assert await session_store.get(hash_token("other")) is None

    await session_store.revoke(hash_token("t1"), T0 + timedelta(hours=1))
    revoked = await session_store.get(hash_token("t1"))
    assert revoked is not None and revoked.revoked_at == T0 + timedelta(hours=1)
    # Revoking again keeps the original instant.
    await session_store.revoke(hash_token("t1"), T0 + timedelta(hours=2))
    again = await session_store.get(hash_token("t1"))
    assert again is not None and again.revoked_at == T0 + timedelta(hours=1)


async def test_revoke_user_sessions_spares_the_excepted_one_and_other_users(
    user_repository: SqlAlchemyUserRepository, session_store: SqlAlchemySessionStore
) -> None:
    await user_repository.add(make_user(1))
    await user_repository.add(make_user(2))
    for token, owner in [("a", 1), ("b", 1), ("c", 2)]:
        await session_store.add(
            Session(hash_token(token), UUID(int=owner), T0, T0 + timedelta(hours=8))
        )

    await session_store.revoke_user_sessions(UUID(int=1), T0, except_token_hash=hash_token("a"))

    revoked = {
        token: (await session_store.get(hash_token(token))).revoked_at is not None  # type: ignore[union-attr]
        for token in "abc"
    }
    assert revoked == {"a": False, "b": True, "c": False}
