from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from fermon.fermentation.domain import (
    AggregatedPoint,
    AggregationBucket,
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
