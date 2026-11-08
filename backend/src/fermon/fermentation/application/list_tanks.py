from fermon.fermentation.application.ports import (
    BatchRepository,
    ReadingRepository,
    TankRepository,
)
from fermon.fermentation.application.tank_overview import TankOverview


class ListTanks:
    def __init__(
        self, tanks: TankRepository, readings: ReadingRepository, batches: BatchRepository
    ) -> None:
        self._tanks = tanks
        self._readings = readings
        self._batches = batches

    async def execute(self) -> list[TankOverview]:
        tanks = await self._tanks.list()
        ids = [t.id for t in tanks]
        latest = await self._readings.latest_per_measurement(ids)
        active = await self._batches.active_for(ids)
        return [
            TankOverview(tank=t, latest=latest.get(t.id, {}), active_batch=active.get(t.id))
            for t in tanks
        ]
