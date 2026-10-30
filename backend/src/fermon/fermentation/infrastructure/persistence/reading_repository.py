from datetime import datetime
from typing import Any

from sqlalchemy import Row, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fermon.fermentation.domain import MeasurementType, Reading, normalize_id, validate_time_range
from fermon.fermentation.infrastructure.persistence.tables import readings


class SqlAlchemyReadingRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def add(self, reading: Reading) -> bool:
        # Idempotent: MQTT QoS 1 may redeliver the same reading. RETURNING yields a row
        # only when the insert happened, so no row means the identity already existed.
        statement = (
            insert(readings)
            .values(
                tank_id=reading.tank_id,
                sensor_id=reading.sensor_id,
                measurement=reading.measurement.value,
                value=reading.value,
                unit=reading.unit,
                recorded_at=reading.recorded_at,
            )
            .on_conflict_do_nothing(constraint="uq_readings_identity")
            .returning(readings.c.tank_id)
        )
        async with self._session_factory() as session, session.begin():
            return (await session.execute(statement)).first() is not None

    async def get(
        self, tank_id: str, sensor_id: str, measurement: MeasurementType, recorded_at: datetime
    ) -> Reading | None:
        statement = select(readings).where(
            readings.c.tank_id == normalize_id("tank_id", tank_id),
            readings.c.sensor_id == normalize_id("sensor_id", sensor_id),
            readings.c.measurement == measurement.value,
            readings.c.recorded_at == recorded_at,
        )
        async with self._session_factory() as session:
            row = (await session.execute(statement)).first()
        return _to_domain(row) if row is not None else None

    async def list_by_tank(self, tank_id: str, start: datetime, end: datetime) -> list[Reading]:
        validate_time_range(start, end)
        statement = (
            select(readings)
            .where(
                readings.c.tank_id == normalize_id("tank_id", tank_id),
                readings.c.recorded_at >= start,
                readings.c.recorded_at < end,
            )
            .order_by(readings.c.recorded_at.asc())
        )
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).all()
        return [_to_domain(row) for row in rows]


def _to_domain(row: Row[Any]) -> Reading:
    return Reading(
        tank_id=row.tank_id,
        sensor_id=row.sensor_id,
        measurement=MeasurementType(row.measurement),
        value=row.value,
        unit=row.unit,
        recorded_at=row.recorded_at,
    )
