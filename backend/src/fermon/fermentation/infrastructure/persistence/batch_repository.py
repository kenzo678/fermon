from collections.abc import Sequence
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fermon.fermentation.domain import (
    ActiveBatchConflictError,
    Batch,
    BatchStatus,
    ConcurrentBatchUpdateError,
    TargetRanges,
    normalize_id,
)
from fermon.fermentation.infrastructure.persistence.tables import batches

ONE_ACTIVE_INDEX = "uq_batches_one_active_per_tank"


class SqlAlchemyBatchRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def add(self, batch: Batch) -> None:
        await self._write(batch, batches.insert().values(**_to_row(batch)))

    async def update(self, batch: Batch) -> None:
        row = _to_row(batch)
        del row["id"]
        statement = (
            update(batches)
            .where(batches.c.id == batch.id, batches.c.version == batch.version - 1)
            .values(**row)
        )
        if await self._write(batch, statement) == 0:
            raise ConcurrentBatchUpdateError(str(batch.id))

    async def _write(self, batch: Batch, statement: Any) -> int:
        """Run the statement in one transaction; the number of rows it matched."""
        try:
            async with self._session_factory() as session, session.begin():
                result = await session.execute(statement)
                return cast(CursorResult[Any], result).rowcount
        except IntegrityError as error:
            # Only the one-active-per-tank index is a business conflict; anything else is a bug.
            if ONE_ACTIVE_INDEX in str(error.orig):
                raise ActiveBatchConflictError(batch.tank_id) from None
            raise

    async def get(self, batch_id: UUID) -> Batch | None:
        async with self._session_factory() as session:
            row = (await session.execute(select(batches).where(batches.c.id == batch_id))).first()
        return _to_domain(row) if row is not None else None

    async def list(
        self, tank_id: str | None = None, status: BatchStatus | None = None
    ) -> list[Batch]:
        statement = select(batches).order_by(batches.c.created_at.desc(), batches.c.id.desc())
        if tank_id is not None:
            statement = statement.where(batches.c.tank_id == normalize_id("tank_id", tank_id))
        if status is not None:
            statement = statement.where(batches.c.status == status.value)
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).all()
        return [_to_domain(row) for row in rows]

    async def get_active(self, tank_id: str) -> Batch | None:
        found = await self.list(tank_id=tank_id, status=BatchStatus.ACTIVE)
        return found[0] if found else None

    async def active_for(self, tank_ids: Sequence[str]) -> dict[str, Batch]:
        if not tank_ids:
            return {}
        statement = select(batches).where(
            batches.c.status == BatchStatus.ACTIVE.value, batches.c.tank_id.in_(list(tank_ids))
        )
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).all()
        return {row.tank_id: _to_domain(row) for row in rows}


def _to_row(batch: Batch) -> dict[str, Any]:
    targets = batch.targets
    return {
        "id": batch.id,
        "tank_id": batch.tank_id,
        "beer_name": batch.beer_name,
        "style": batch.style,
        "template": batch.template.value,
        "status": batch.status.value,
        "temperature_min": targets.temperature_min,
        "temperature_max": targets.temperature_max,
        "pressure_max": targets.pressure_max,
        "pressure_min": targets.pressure_min,
        "expected_final_abv": targets.expected_final_abv,
        "planned_start": batch.planned_start,
        "expected_end": batch.expected_end,
        "started_at": batch.started_at,
        "finished_at": batch.finished_at,
        "notes": batch.notes,
        "created_at": batch.created_at,
        "version": batch.version,
    }


def _to_domain(row: Any) -> Batch:
    return Batch(
        id=row.id,
        tank_id=row.tank_id,
        beer_name=row.beer_name,
        style=row.style,
        template=row.template,
        targets=TargetRanges(
            temperature_min=row.temperature_min,
            temperature_max=row.temperature_max,
            pressure_max=row.pressure_max,
            pressure_min=row.pressure_min,
            expected_final_abv=row.expected_final_abv,
        ),
        status=row.status,
        planned_start=row.planned_start,
        expected_end=row.expected_end,
        started_at=row.started_at,
        finished_at=row.finished_at,
        notes=row.notes,
        created_at=row.created_at,
        version=row.version,
    )
