from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fermon.fermentation.domain import MeasurementType, Reading, normalize_id
from fermon.fermentation.infrastructure.persistence.tables import readings


class SqlAlchemyReadingRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def add(self, reading: Reading) -> None:
        # Idempotent: MQTT QoS 1 may redeliver the same reading.
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
        )
        async with self._session_factory() as session, session.begin():
            await session.execute(statement)

    async def list_by_tank(self, tank_id: str, start: datetime, end: datetime) -> list[Reading]:
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
        return [
            Reading(
                tank_id=row.tank_id,
                sensor_id=row.sensor_id,
                measurement=MeasurementType(row.measurement),
                value=row.value,
                unit=row.unit,
                recorded_at=row.recorded_at,
            )
            for row in rows
        ]
