from datetime import datetime

from fermon.fermentation.application.ports import ReadingRepository
from fermon.fermentation.domain import InvalidTimeRangeError, Reading, normalize_id


class ListReadings:
    def __init__(self, repository: ReadingRepository) -> None:
        self._repository = repository

    async def execute(self, tank_id: str, start: datetime, end: datetime) -> list[Reading]:
        tank_id = normalize_id("tank_id", tank_id)
        for name, moment in (("start", start), ("end", end)):
            if moment.tzinfo is None or moment.utcoffset() is None:
                raise InvalidTimeRangeError(f"{name} must be timezone-aware")
        if start >= end:
            raise InvalidTimeRangeError("start must be before end")
        return await self._repository.list_by_tank(tank_id, start, end)
