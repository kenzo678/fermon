from datetime import datetime

from fermon.fermentation.domain import MeasurementType, Reading


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
