from datetime import datetime
from typing import Protocol

from fermon.fermentation.domain import MeasurementType, Reading


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
