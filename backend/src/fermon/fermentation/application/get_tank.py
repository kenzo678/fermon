from fermon.fermentation.application.ports import ReadingRepository, TankRepository
from fermon.fermentation.application.tank_overview import TankOverview
from fermon.fermentation.domain import TankNotFoundError, normalize_id


class GetTank:
    def __init__(self, tanks: TankRepository, readings: ReadingRepository) -> None:
        self._tanks = tanks
        self._readings = readings

    async def execute(self, tank_id: str) -> TankOverview:
        tank_id = normalize_id("tank_id", tank_id)
        tank = await self._tanks.get(tank_id)
        if tank is None:
            raise TankNotFoundError(tank_id)
        latest = await self._readings.latest_per_measurement([tank.id])
        return TankOverview(tank=tank, latest=latest.get(tank.id, {}))
