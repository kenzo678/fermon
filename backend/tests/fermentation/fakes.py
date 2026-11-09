from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from fermon.fermentation.domain import (
    ActiveBatchConflictError,
    AggregatedPoint,
    AggregationBucket,
    Alert,
    AlertKind,
    AlertStatus,
    Batch,
    BatchStatus,
    ConcurrentAlertUpdateError,
    ConcurrentBatchUpdateError,
    MeasurementType,
    Reading,
    Tank,
)


def _identity(reading: Reading) -> tuple[str, str, MeasurementType, datetime]:
    return (reading.tank_id, reading.sensor_id, reading.measurement, reading.recorded_at)


class InMemoryReadingRepository:
    def __init__(self) -> None:
        self.readings: list[Reading] = []

    async def add(self, reading: Reading) -> bool:
        if await self.get(*_identity(reading)) is not None:
            return False
        self.readings.append(reading)
        return True

    async def get(
        self, tank_id: str, sensor_id: str, measurement: MeasurementType, recorded_at: datetime
    ) -> Reading | None:
        key = (tank_id, sensor_id, measurement, recorded_at)
        return next((r for r in self.readings if _identity(r) == key), None)

    async def list_by_tank(self, tank_id: str, start: datetime, end: datetime) -> list[Reading]:
        matching = [
            r for r in self.readings if r.tank_id == tank_id and start <= r.recorded_at < end
        ]
        return sorted(matching, key=lambda r: r.recorded_at)

    async def latest_per_measurement(
        self, tank_ids: Sequence[str]
    ) -> dict[str, dict[MeasurementType, Reading]]:
        latest: dict[str, dict[MeasurementType, Reading]] = {}
        # Same tie-break as the SQL adapter: newest recorded_at, then highest sensor_id.
        for r in sorted(self.readings, key=lambda r: (r.recorded_at, r.sensor_id)):
            if r.tank_id in tank_ids:
                latest.setdefault(r.tank_id, {})[r.measurement] = r
        return latest

    async def streak_start(
        self,
        tank_id: str,
        measurement: MeasurementType,
        low: float | None,
        high: float | None,
        in_range: bool,
        since: datetime,
        until: datetime,
    ) -> datetime | None:
        def inside(value: float) -> bool:
            return (low is None or value >= low) and (high is None or value <= high)

        window = [
            r
            for r in self.readings
            if r.tank_id == tank_id
            and r.measurement is measurement
            and since <= r.recorded_at <= until
        ]
        # Same semantics as the SQL adapter: readings sharing an instant with one of the other
        # class do not belong to the streak, whatever the insertion order.
        other = [r.recorded_at for r in window if inside(r.value) is not in_range]
        last_other = max(other, default=None)
        wanted = [
            r.recorded_at
            for r in window
            if inside(r.value) is in_range and (last_other is None or r.recorded_at > last_other)
        ]
        return min(wanted, default=None)

    async def aggregated(
        self,
        tank_id: str,
        bucket: AggregationBucket,
        start: datetime,
        end: datetime,
        measurements: Sequence[MeasurementType],
    ) -> list[AggregatedPoint]:
        size = int(bucket.interval.total_seconds())
        groups: dict[tuple[datetime, MeasurementType], list[float]] = {}
        for r in self.readings:
            if r.tank_id != tank_id or r.measurement not in measurements:
                continue
            seconds = int(r.recorded_at.timestamp())
            bucket_start = datetime.fromtimestamp(seconds - seconds % size, UTC)
            if start <= bucket_start < end:
                groups.setdefault((bucket_start, r.measurement), []).append(r.value)
        return [
            AggregatedPoint(at, m, sum(v) / len(v), min(v), max(v), len(v))
            for (at, m), v in sorted(groups.items(), key=lambda item: (item[0][0], item[0][1]))
        ]


class InMemoryTankRepository:
    def __init__(self) -> None:
        self.tanks: dict[str, Tank] = {}

    async def ensure(self, tank_id: str, seen_at: datetime) -> None:
        current = self.tanks.get(tank_id)
        if current is None or seen_at < current.first_seen_at:
            display_name = current.display_name if current else None
            self.tanks[tank_id] = Tank(id=tank_id, display_name=display_name, first_seen_at=seen_at)

    async def get(self, tank_id: str) -> Tank | None:
        return self.tanks.get(tank_id)

    async def list(self) -> list[Tank]:
        return sorted(self.tanks.values(), key=lambda t: t.id)


class InMemoryBatchRepository:
    """Mirrors the SQL adapter, including the one-active-batch-per-tank invariant."""

    def __init__(self) -> None:
        self.batches: dict[UUID, Batch] = {}

    def _check_active(self, batch: Batch) -> None:
        if batch.status is BatchStatus.ACTIVE and any(
            other.tank_id == batch.tank_id
            and other.status is BatchStatus.ACTIVE
            and other.id != batch.id
            for other in self.batches.values()
        ):
            raise ActiveBatchConflictError(batch.tank_id)

    async def add(self, batch: Batch) -> None:
        self._check_active(batch)
        self.batches[batch.id] = batch

    async def update(self, batch: Batch) -> None:
        current = self.batches.get(batch.id)
        if current is None or current.version != batch.version - 1:
            raise ConcurrentBatchUpdateError(str(batch.id))
        self._check_active(batch)
        self.batches[batch.id] = batch

    async def get(self, batch_id: UUID) -> Batch | None:
        return self.batches.get(batch_id)

    async def list(
        self, tank_id: str | None = None, status: BatchStatus | None = None
    ) -> list[Batch]:
        matching = [
            b
            for b in self.batches.values()
            if (tank_id is None or b.tank_id == tank_id) and (status is None or b.status is status)
        ]
        return sorted(matching, key=lambda b: (b.created_at, str(b.id)), reverse=True)

    async def get_active(self, tank_id: str) -> Batch | None:
        found = await self.list(tank_id=tank_id, status=BatchStatus.ACTIVE)
        return found[0] if found else None

    async def active_for(self, tank_ids: Sequence[str]) -> dict[str, Batch]:
        active = await self.list(status=BatchStatus.ACTIVE)
        return {b.tank_id: b for b in active if b.tank_id in tank_ids}


class InMemoryAlertRepository:
    """Mirrors the SQL adapter, including one unresolved alert per (tank, kind, measurement)."""

    def __init__(self) -> None:
        self.alerts: dict[UUID, Alert] = {}

    def _key(self, alert: Alert) -> tuple[str, AlertKind, MeasurementType | None]:
        return (alert.tank_id, alert.kind, alert.measurement)

    async def add(self, alert: Alert) -> bool:
        if alert.is_unresolved and any(
            other.is_unresolved and self._key(other) == self._key(alert)
            for other in self.alerts.values()
        ):
            return False
        self.alerts[alert.id] = alert
        return True

    async def update(self, alert: Alert) -> None:
        current = self.alerts.get(alert.id)
        if current is None or current.version != alert.version - 1:
            raise ConcurrentAlertUpdateError(str(alert.id))
        self.alerts[alert.id] = alert

    async def get(self, alert_id: UUID) -> Alert | None:
        return self.alerts.get(alert_id)

    async def list(
        self,
        tank_id: str | None = None,
        statuses: Sequence[AlertStatus] | None = None,
        kind: AlertKind | None = None,
        batch_id: UUID | None = None,
        limit: int | None = None,
    ) -> list[Alert]:
        matching = [
            a
            for a in self.alerts.values()
            if (tank_id is None or a.tank_id == tank_id)
            and (statuses is None or a.status in statuses)
            and (kind is None or a.kind is kind)
            and (batch_id is None or a.batch_id == batch_id)
        ]
        newest_first = sorted(matching, key=lambda a: (a.opened_at, str(a.id)), reverse=True)
        return newest_first[:limit]

    async def count_unresolved(self, tank_ids: Sequence[str]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for a in self.alerts.values():
            if a.is_unresolved and a.tank_id in tank_ids:
                counts[a.tank_id] = counts.get(a.tank_id, 0) + 1
        return counts

    async def get_unresolved(
        self, tank_id: str, kind: AlertKind, measurement: MeasurementType | None
    ) -> Alert | None:
        return next(
            (
                a
                for a in self.alerts.values()
                if a.is_unresolved
                and (a.tank_id, a.kind, a.measurement) == (tank_id, kind, measurement)
            ),
            None,
        )
