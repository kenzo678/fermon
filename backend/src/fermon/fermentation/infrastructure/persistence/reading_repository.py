from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import Row, Text, column, select, true, values
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fermon.fermentation.domain import (
    AggregatedPoint,
    AggregationBucket,
    MeasurementType,
    Reading,
    normalize_id,
    validate_time_range,
)
from fermon.fermentation.infrastructure.persistence.tables import (
    readings,
    readings_1h,
    readings_1m,
)


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

    async def latest_per_measurement(
        self, tank_ids: Sequence[str]
    ) -> dict[str, dict[MeasurementType, Reading]]:
        if not tank_ids:
            return {}
        # One LATERAL "newest row" lookup per (tank, measurement) pair. Each probe walks
        # ix_readings_tank_id_recorded_at (tank_id, recorded_at DESC) and stops at the first row
        # of that measurement, so cost is ~#tanks x #measurements index probes regardless of
        # history size. DISTINCT ON (tank_id, measurement) would instead read every reading of
        # every requested tank on the hypertable.
        tank_values = values(column("id", Text), name="wanted_tanks").data(
            [(normalize_id("tank_id", t),) for t in tank_ids]
        )
        measurement_values = values(column("name", Text), name="wanted_measurements").data(
            [(m.value,) for m in MeasurementType]
        )
        newest = (
            select(readings)
            .where(
                readings.c.tank_id == tank_values.c.id,
                readings.c.measurement == measurement_values.c.name,
            )
            # sensor_id breaks same-instant ties so the result is stable across calls.
            .order_by(readings.c.recorded_at.desc(), readings.c.sensor_id.desc())
            .limit(1)
            .lateral("newest")
        )
        statement = select(newest).select_from(
            tank_values.join(measurement_values, true()).join(newest, true())
        )
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).all()
        latest: dict[str, dict[MeasurementType, Reading]] = {}
        for row in rows:
            reading = _to_domain(row)
            latest.setdefault(reading.tank_id, {})[reading.measurement] = reading
        return latest

    async def aggregated(
        self,
        tank_id: str,
        bucket: AggregationBucket,
        start: datetime,
        end: datetime,
        measurements: Sequence[MeasurementType],
    ) -> list[AggregatedPoint]:
        validate_time_range(start, end)
        if not measurements:
            return []
        view = _AGGREGATE_VIEWS[bucket]
        statement = (
            select(
                view.c.bucket,
                view.c.measurement,
                (view.c.sum_value / view.c.sample_count).label("avg"),
                view.c.min_value,
                view.c.max_value,
                view.c.sample_count,
            )
            .where(
                view.c.tank_id == normalize_id("tank_id", tank_id),
                view.c.measurement.in_([m.value for m in measurements]),
                view.c.bucket >= start,
                view.c.bucket < end,
            )
            .order_by(view.c.bucket.asc(), view.c.measurement.asc())
        )
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).all()
        return [
            AggregatedPoint(
                bucket_start=row.bucket,
                measurement=MeasurementType(row.measurement),
                avg=row.avg,
                min=row.min_value,
                max=row.max_value,
                count=row.sample_count,
            )
            for row in rows
        ]


_AGGREGATE_VIEWS = {
    AggregationBucket.ONE_MINUTE: readings_1m,
    AggregationBucket.ONE_HOUR: readings_1h,
}


def _to_domain(row: Row[Any]) -> Reading:
    return Reading(
        tank_id=row.tank_id,
        sensor_id=row.sensor_id,
        measurement=MeasurementType(row.measurement),
        value=row.value,
        unit=row.unit,
        recorded_at=row.recorded_at,
    )
