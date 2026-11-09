from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fermon.fermentation.domain import (
    Alert,
    AlertKind,
    AlertStatus,
    ConcurrentAlertUpdateError,
    MeasurementType,
    normalize_id,
)
from fermon.fermentation.infrastructure.persistence.tables import alerts

ONE_UNRESOLVED_INDEX = "uq_alerts_one_unresolved"


class SqlAlchemyAlertRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def add(self, alert: Alert) -> bool:
        try:
            async with self._session_factory() as session, session.begin():
                await session.execute(alerts.insert().values(**_to_row(alert)))
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
        if matched == 0:
            raise ConcurrentAlertUpdateError(str(alert.id))

    async def get(self, alert_id: UUID) -> Alert | None:
        async with self._session_factory() as session:
            row = (await session.execute(select(alerts).where(alerts.c.id == alert_id))).first()
        return _to_domain(row) if row is not None else None

    async def list(
        self,
        tank_id: str | None = None,
        status: AlertStatus | None = None,
        kind: AlertKind | None = None,
        batch_id: UUID | None = None,
    ) -> list[Alert]:
        statement = select(alerts).order_by(alerts.c.opened_at.desc(), alerts.c.id.desc())
        if tank_id is not None:
            statement = statement.where(alerts.c.tank_id == normalize_id("tank_id", tank_id))
        if status is not None:
            statement = statement.where(alerts.c.status == status.value)
        if kind is not None:
            statement = statement.where(alerts.c.kind == kind.value)
        if batch_id is not None:
            statement = statement.where(alerts.c.batch_id == batch_id)
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).all()
        return [_to_domain(row) for row in rows]

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
