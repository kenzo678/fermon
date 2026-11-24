from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Update, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fermon.identity.domain import Session
from fermon.identity.infrastructure.persistence.tables import sessions


def revocation_statement(condition: Any, at: datetime) -> Update:
    """Marks the matching, still-live sessions as revoked at ``at``."""
    return update(sessions).where(condition, sessions.c.revoked_at.is_(None)).values(revoked_at=at)


class SqlAlchemySessionStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def add(self, session: Session) -> None:
        row = {
            "token_hash": session.token_hash,
            "user_id": session.user_id,
            "created_at": session.created_at,
            "expires_at": session.expires_at,
            "revoked_at": session.revoked_at,
        }
        async with self._session_factory() as db, db.begin():
            await db.execute(sessions.insert().values(**row))

    async def purge_expired(self, now: datetime) -> None:
        async with self._session_factory() as db, db.begin():
            await db.execute(delete(sessions).where(sessions.c.expires_at <= now))

    async def get(self, token_hash: str) -> Session | None:
        statement = select(sessions).where(sessions.c.token_hash == token_hash)
        async with self._session_factory() as db:
            row = (await db.execute(statement)).first()
        if row is None:
            return None
        return Session(row.token_hash, row.user_id, row.created_at, row.expires_at, row.revoked_at)

    async def revoke(self, token_hash: str, at: datetime) -> None:
        await self._revoke(sessions.c.token_hash == token_hash, at)

    async def revoke_user_sessions(
        self, user_id: UUID, at: datetime, except_token_hash: str | None = None
    ) -> None:
        condition = sessions.c.user_id == user_id
        if except_token_hash is not None:
            condition = condition & (sessions.c.token_hash != except_token_hash)
        await self._revoke(condition, at)

    async def _revoke(self, condition: Any, at: datetime) -> None:
        async with self._session_factory() as db, db.begin():
            await db.execute(revocation_statement(condition, at))
