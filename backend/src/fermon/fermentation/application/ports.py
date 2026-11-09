from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from fermon.fermentation.domain import (
    AggregatedPoint,
    AggregationBucket,
    Alert,
    AlertKind,
    AlertStatus,
    Batch,
    BatchStatus,
    MeasurementType,
    Reading,
    Tank,
)


class ReadingRepository(Protocol):
    async def add(self, reading: Reading) -> bool:
        """Store the reading. False if one with the same identity already existed.

        Identity is (tank_id, sensor_id, measurement, recorded_at); the first write wins.
        """
        ...

    async def get(
        self, tank_id: str, sensor_id: str, measurement: MeasurementType, recorded_at: datetime
    ) -> Reading | None:
        """The stored reading with this identity, if any."""
        ...

    async def list_by_tank(self, tank_id: str, start: datetime, end: datetime) -> list[Reading]:
        """Readings of a tank in the half-open range [start, end), oldest first."""
        ...

    async def latest_per_measurement(
        self, tank_ids: Sequence[str]
    ) -> dict[str, dict[MeasurementType, Reading]]:
        """The most recent reading of each measurement, for each given tank.

        Tanks (or measurements) without readings are absent from the result.
        """
        ...

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
        """When the tank's current run of in-range (or out-of-range) readings began.

        Looks at the readings of the tank and measurement (all sensors together) with
        ``recorded_at`` in [since, until]. A reading is in range when ``low <= value <= high``
        (a ``None`` limit is unbounded). Returns the earliest ``recorded_at`` of the readings of
        the requested class that come after the last reading of the opposite class, so it is the
        start of the uninterrupted run that ends the window; ``None`` when the newest reading in
        the window is of the other class or the window is empty.
        """
        ...

    async def aggregated(
        self,
        tank_id: str,
        bucket: AggregationBucket,
        start: datetime,
        end: datetime,
        measurements: Sequence[MeasurementType],
    ) -> list[AggregatedPoint]:
        """Per-measurement statistics (all sensors together) of buckets starting in [start, end).

        Ordered by bucket start, then measurement. Empty buckets are absent.
        """
        ...


class TankRepository(Protocol):
    async def ensure(self, tank_id: str, seen_at: datetime) -> None:
        """Register the tank, first seen at ``seen_at``, unless it already exists (no-op then)."""
        ...

    async def get(self, tank_id: str) -> Tank | None:
        """The registered tank with this id, if any."""
        ...

    async def list(self) -> list[Tank]:
        """All registered tanks, sorted by id."""
        ...


class BatchRepository(Protocol):
    async def add(self, batch: Batch) -> None:
        """Store a new batch. Raises ActiveBatchConflictError if it would be a second active one."""
        ...

    async def update(self, batch: Batch) -> None:
        """Store a new revision of an existing batch (optimistic concurrency).

        Succeeds only if the stored version is ``batch.version - 1``; otherwise (changed or
        missing meanwhile) raises ConcurrentBatchUpdateError and writes nothing. Raises
        ActiveBatchConflictError if the tank would end up with two active batches.
        """
        ...

    async def get(self, batch_id: UUID) -> Batch | None:
        """The batch with this id, if any."""
        ...

    async def list(
        self, tank_id: str | None = None, status: BatchStatus | None = None
    ) -> list[Batch]:
        """Batches matching the optional filters, newest first (by creation time)."""
        ...

    async def get_active(self, tank_id: str) -> Batch | None:
        """The tank's active batch, if any."""
        ...

    async def active_for(self, tank_ids: Sequence[str]) -> dict[str, Batch]:
        """The active batch of each given tank (one query); tanks without one are absent."""
        ...


class AlertRepository(Protocol):
    async def add(self, alert: Alert) -> bool:
        """Store a new alert. False if the tank already has an unresolved alert of that kind
        (and measurement), in which case nothing is written: opening is idempotent.
        """
        ...

    async def update(self, alert: Alert) -> None:
        """Store a new revision of an existing alert (optimistic concurrency).

        Succeeds only if the stored version is ``alert.version - 1``; otherwise (changed or
        missing meanwhile) raises ConcurrentAlertUpdateError and writes nothing.
        """
        ...

    async def get(self, alert_id: UUID) -> Alert | None:
        """The alert with this id, if any."""
        ...

    async def list(
        self,
        tank_id: str | None = None,
        status: AlertStatus | None = None,
        kind: AlertKind | None = None,
        batch_id: UUID | None = None,
    ) -> list[Alert]:
        """Alerts matching the optional filters, newest first (by opening time)."""
        ...

    async def get_unresolved(
        self, tank_id: str, kind: AlertKind, measurement: MeasurementType | None
    ) -> Alert | None:
        """The open or acknowledged alert of this tank, kind and measurement, if any."""
        ...
