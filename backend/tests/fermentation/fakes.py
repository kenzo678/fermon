from datetime import datetime

from fermon.fermentation.domain import Reading


class InMemoryReadingRepository:
    def __init__(self) -> None:
        self.readings: list[Reading] = []

    async def add(self, reading: Reading) -> None:
        self.readings.append(reading)

    async def list_by_tank(self, tank_id: str, start: datetime, end: datetime) -> list[Reading]:
        matching = [
            r for r in self.readings if r.tank_id == tank_id and start <= r.recorded_at < end
        ]
        return sorted(matching, key=lambda r: r.recorded_at)
