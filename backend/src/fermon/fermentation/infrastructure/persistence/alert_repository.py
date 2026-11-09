import logging
from collections.abc import Sequence
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, Executable, func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fermon.fermentation.domain import (
    Alert,
    AlertKind,
    AlertStatus,
    ConcurrentAlertUpdateError,
    MeasurementType,
    normalize_id,
)
from fermon.fermentation.infrastructure.persistence.reading_repository import (
    MAX_NOTIFY_PAYLOAD_BYTES,
)
from fermon.fermentation.infrastructure.persistence.tables import alerts
from fermon.fermentation.infrastructure.realtime.payload import ALERTS_CHANNEL, encode_alert

logger = logging.getLogger(__name__)

ONE_UNRESOLVED_INDEX = "uq_alerts_one_unresolved"


def _notify_statement(payload: str) -> Executable:
    return select(func.pg_notify(ALERTS_CHANNEL, payload))


class SqlAlchemyAlertRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def add(self, alert: Alert) -> bool:
        try:
            async with self._session_factory() as session, session.begin():
                await session.execute(alerts.insert().values(**_to_row(alert)))
                await self._notify(session, alert)
        except IntegrityError as error:
            # Another unresolved alert for the same key is the idempotent outcome of a racing
            # evaluation; any other violation (FK, CHECK) is a bug and must surface.
            if ONE_UNRESOLVED_INDEX in str(error.orig):
                return False
            raise
        return True

    async def update(self, alert: Alert) -> None:
        row = _to_row(alert)
        del row["id"]
        statement = (
            update(alerts)
            .where(alerts.c.id == alert.id, alerts.c.version == alert.version - 1)
            .values(**row)
        )
        async with self._session_factory() as session, session.begin():
            result = await session.execute(statement)
            matched = cast(CursorResult[Any], result).rowcount
            if matched:
                await self._notify(session, alert)
        if matched == 0:
            raise ConcurrentAlertUpdateError(str(alert.id))

    async def _notify(self, session: AsyncSession, alert: Alert) -> None:
        """Best-effort realtime signal; it must never cost the caller a stored alert write.

        Queued in the writing transaction (delivered on commit, never for a rolled-back write);
        a SAVEPOINT confines a NOTIFY error to the NOTIFY, so the write still commits.
        """
        payload = encode_alert(alert)
        if len(payload.encode()) > MAX_NOTIFY_PAYLOAD_BYTES:
            logger.warning(
                "skipping realtime notify: payload exceeds %d bytes", MAX_NOTIFY_PAYLOAD_BYTES
            )
            return
        try:
            async with session.begin_nested():
                await session.execute(_notify_statement(payload))
        except SQLAlchemyError:
            logger.warning("realtime notify failed; the alert was stored", exc_info=True)

    async def get(self, alert_id: UUID) -> Alert | None:
        async with self._session_factory() as session:
            row = (await session.execute(select(alerts).where(alerts.c.id == alert_id))).first()
        return _to_domain(row) if row is not None else None

    async def list(
        self,
        tank_id: str | None = None,
        statuses: Sequence[AlertStatus] | None = None,
        kind: AlertKind | None = None,
        batch_id: UUID | None = None,
        limit: int | None = None,
    ) -> list[Alert]:
        statement = select(alerts).order_by(alerts.c.opened_at.desc(), alerts.c.id.desc())
        if tank_id is not None:
            statement = statement.where(alerts.c.tank_id == normalize_id("tank_id", tank_id))
        if statuses is not None:
            statement = statement.where(alerts.c.status.in_([s.value for s in statuses]))
        if kind is not None:
            statement = statement.where(alerts.c.kind == kind.value)
        if batch_id is not None:
            statement = statement.where(alerts.c.batch_id == batch_id)
        if limit is not None:
            statement = statement.limit(limit)
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).all()
        return [_to_domain(row) for row in rows]

    async def count_unresolved(self, tank_ids: Sequence[str]) -> dict[str, int]:
        if not tank_ids:
            return {}
        statement = (
            select(alerts.c.tank_id, func.count())
            .where(
                alerts.c.tank_id.in_(tank_ids),
                alerts.c.status != AlertStatus.RESOLVED.value,
            )
            .group_by(alerts.c.tank_id)
        )
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).all()
        return {tank_id: count for tank_id, count in rows}

    async def get_unresolved(
        self, tank_id: str, kind: AlertKind, measurement: MeasurementType | None
    ) -> Alert | None:
        statement = select(alerts).where(
            alerts.c.tank_id == normalize_id("tank_id", tank_id),
            alerts.c.kind == kind.value,
            alerts.c.status != AlertStatus.RESOLVED.value,
            alerts.c.measurement.is_(None)
            if measurement is None
            else alerts.c.measurement == measurement.value,
        )
        async with self._session_factory() as session:
            row = (await session.execute(statement)).first()
        return _to_domain(row) if row is not None else None


def _to_row(alert: Alert) -> dict[str, Any]:
    return {
        "id": alert.id,
        "tank_id": alert.tank_id,
        "batch_id": alert.batch_id,
        "kind": alert.kind.value,
        "measurement": alert.measurement.value if alert.measurement else None,
        "status": alert.status.value,
        "opened_at": alert.opened_at,
        "acknowledged_at": alert.acknowledged_at,
        "resolved_at": alert.resolved_at,
        "details": alert.details,
        "version": alert.version,
    }


def _to_domain(row: Any) -> Alert:
    return Alert(
        id=row.id,
        tank_id=row.tank_id,
        batch_id=row.batch_id,
        kind=AlertKind(row.kind),
        measurement=MeasurementType(row.measurement) if row.measurement else None,
        status=AlertStatus(row.status),
        opened_at=row.opened_at,
        acknowledged_at=row.acknowledged_at,
        resolved_at=row.resolved_at,
        details=row.details,
        version=row.version,
    )
