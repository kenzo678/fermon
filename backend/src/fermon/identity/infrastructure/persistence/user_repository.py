from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, Update, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fermon.identity.domain import ConcurrentUserUpdateError, EmailAlreadyUsedError, Role, User
from fermon.identity.infrastructure.persistence.tables import users

EMAIL_INDEX = "uq_users_email_lower"


class SqlAlchemyUserRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def add(self, user: User) -> None:
        try:
            async with self._session_factory() as session, session.begin():
                await session.execute(users.insert().values(**_to_row(user)))
        except IntegrityError as error:
            if EMAIL_INDEX in str(error.orig):
                raise EmailAlreadyUsedError(user.email) from None
            raise

    async def update(self, user: User) -> None:
        statement = update_statement(user)
        async with self._session_factory() as session, session.begin():
            result = await session.execute(statement)
        if cast(CursorResult[Any], result).rowcount == 0:
            raise ConcurrentUserUpdateError(str(user.id))

    async def get(self, user_id: UUID) -> User | None:
        return await self._one(users.c.id == user_id)

    async def get_by_email(self, email: str) -> User | None:
        return await self._one(func.lower(users.c.email) == email.lower())

    async def _one(self, condition: Any) -> User | None:
        async with self._session_factory() as session:
            row = (await session.execute(select(users).where(condition))).first()
        return _to_domain(row) if row is not None else None

    async def list(self) -> list[User]:
        statement = select(users).order_by(users.c.created_at, users.c.email)
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).all()
        return [_to_domain(row) for row in rows]

    async def count_active_admins(self) -> int:
        statement = (
            select(func.count())
            .select_from(users)
            .where(users.c.role == Role.ADMIN.value, users.c.active.is_(True))
        )
        async with self._session_factory() as session:
            return int(await session.scalar(statement) or 0)


def update_statement(user: User) -> Update:
    """UPDATE guarded by the previous version (optimistic locking); check ``rowcount``."""
    row = _to_row(user)
    del row["id"]
    return (update(users).where(users.c.id == user.id, users.c.version == user.version - 1)).values(
        **row
    )


def _to_row(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role.value,
        "password_hash": user.password_hash,
        "must_change_password": user.must_change_password,
        "active": user.active,
        "created_at": user.created_at,
        "version": user.version,
    }


def _to_domain(row: Any) -> User:
    return User(
        id=row.id,
        email=row.email,
        display_name=row.display_name,
        role=Role(row.role),
        password_hash=row.password_hash,
        must_change_password=row.must_change_password,
        active=row.active,
        created_at=row.created_at,
        version=row.version,
    )
