from fermon.fermentation.application.ports import ReadingRepository, TankRepository
from fermon.fermentation.application.tank_overview import TankOverview


class ListTanks:
    def __init__(self, tanks: TankRepository, readings: ReadingRepository) -> None:
        self._tanks = tanks
        self._readings = readings

    async def execute(self) -> list[TankOverview]:
        tanks = await self._tanks.list()
        latest = await self._readings.latest_per_measurement([t.id for t in tanks])
        return [TankOverview(tank=t, latest=latest.get(t.id, {})) for t in tanks]
