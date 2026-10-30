from collections.abc import Sequence
from datetime import UTC, datetime

from fermon.fermentation.domain import (
    AggregatedPoint,
    AggregationBucket,
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
