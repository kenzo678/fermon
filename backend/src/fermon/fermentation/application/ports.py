from datetime import datetime
from typing import Protocol

from fermon.fermentation.domain import Reading


class ReadingRepository(Protocol):
    async def add(self, reading: Reading) -> None: ...

    async def list_by_tank(self, tank_id: str, start: datetime, end: datetime) -> list[Reading]:
        """Readings of a tank in the half-open range [start, end), oldest first."""
        ...
