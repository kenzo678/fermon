from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from fermon.fermentation.domain import (
    AggregatedPoint,
    AggregationBucket,
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
