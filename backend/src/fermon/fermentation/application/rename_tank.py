from fermon.fermentation.application.get_tank import GetTank
from fermon.fermentation.application.ports import TankRepository
from fermon.fermentation.application.tank_overview import TankOverview
from fermon.fermentation.domain import TankNotFoundError, normalize_id


class RenameTank:
    """Set or clear a tank's display name. Last write wins: the name carries no version."""

    def __init__(self, tanks: TankRepository, get_tank: GetTank) -> None:
        self._tanks = tanks
        self._get_tank = get_tank

    async def execute(self, tank_id: str, display_name: str | None) -> TankOverview:
        tank_id = normalize_id("tank_id", tank_id)
        tank = await self._tanks.get(tank_id)
        if tank is None:
            raise TankNotFoundError(tank_id)
        renamed = tank.rename(display_name)
        if not await self._tanks.set_display_name(tank_id, renamed.display_name):
            raise TankNotFoundError(tank_id)  # unreachable: tanks are never deleted
        return await self._get_tank.execute(tank_id)
