from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fermon.fermentation.domain import Tank, normalize_id
from fermon.fermentation.infrastructure.persistence.tables import tanks


class SqlAlchemyTankRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def ensure(self, tank_id: str, seen_at: datetime) -> None:
        # Idempotent and race-free: concurrent first readings of a tank collapse into one row.
        # Readings may arrive out of order (QoS 1 redelivery, backlog after an outage), so the
        # earliest ``seen_at`` wins, matching the migration backfill's min(recorded_at).
        statement = insert(tanks).values(id=normalize_id("tank_id", tank_id), first_seen_at=seen_at)
        statement = statement.on_conflict_do_update(
            index_elements=[tanks.c.id],
            set_={"first_seen_at": statement.excluded.first_seen_at},
            # Only rewrite when strictly earlier, so the hot ingest path does not write a new row
            # version (WAL, bloat) on every reading. Postgres still locks the conflicting row, so
            # concurrent ingests for the same tank serialize briefly here.
            where=statement.excluded.first_seen_at < tanks.c.first_seen_at,
        )
        async with self._session_factory() as session, session.begin():
            await session.execute(statement)

    async def get(self, tank_id: str) -> Tank | None:
        statement = select(tanks).where(tanks.c.id == normalize_id("tank_id", tank_id))
        async with self._session_factory() as session:
            row = (await session.execute(statement)).first()
        return _to_domain(row) if row is not None else None

    async def list(self) -> list[Tank]:
        async with self._session_factory() as session:
            rows = (await session.execute(select(tanks).order_by(tanks.c.id))).all()
        return [_to_domain(row) for row in rows]


def _to_domain(row: Any) -> Tank:
    return Tank(id=row.id, display_name=row.display_name, first_seen_at=row.first_seen_at)
