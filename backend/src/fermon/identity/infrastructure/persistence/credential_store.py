from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fermon.identity.domain import ConcurrentUserUpdateError, User
from fermon.identity.infrastructure.persistence.session_store import revocation_statement
from fermon.identity.infrastructure.persistence.tables import sessions
from fermon.identity.infrastructure.persistence.user_repository import update_statement


class SqlAlchemyCredentialStore:
    """Writes a user and revokes their sessions in a single database transaction."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def replace_user_and_revoke_sessions(
        self, user: User, at: datetime, except_token_hash: str | None = None
    ) -> None:
        condition: Any = sessions.c.user_id == user.id
        if except_token_hash is not None:
            condition = condition & (sessions.c.token_hash != except_token_hash)
        # Any exception leaves the ``begin()`` block, which rolls the password write back too.
        async with self._session_factory() as db, db.begin():
            result = await db.execute(update_statement(user))
            if cast(CursorResult[Any], result).rowcount == 0:
                raise ConcurrentUserUpdateError(str(user.id))
            await db.execute(revocation_statement(condition, at))
