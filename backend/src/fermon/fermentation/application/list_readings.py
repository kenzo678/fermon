from datetime import datetime

from fermon.fermentation.application.ports import ReadingRepository
from fermon.fermentation.domain import Reading, normalize_id, validate_time_range


class ListReadings:
    def __init__(self, repository: ReadingRepository) -> None:
        self._repository = repository

    async def execute(self, tank_id: str, start: datetime, end: datetime) -> list[Reading]:
        tank_id = normalize_id("tank_id", tank_id)
        validate_time_range(start, end)
        return await self._repository.list_by_tank(tank_id, start, end)
