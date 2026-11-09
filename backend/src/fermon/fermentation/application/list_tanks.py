from fermon.fermentation.application.ports import (
    AlertRepository,
    BatchRepository,
    ReadingRepository,
    TankRepository,
)
from fermon.fermentation.application.tank_overview import TankOverview


class ListTanks:
    def __init__(
        self,
        tanks: TankRepository,
        readings: ReadingRepository,
        batches: BatchRepository,
        alerts: AlertRepository,
    ) -> None:
        self._tanks = tanks
        self._readings = readings
        self._batches = batches
        self._alerts = alerts

    async def execute(self) -> list[TankOverview]:
        tanks = await self._tanks.list()
        ids = [t.id for t in tanks]
        latest = await self._readings.latest_per_measurement(ids)
        active = await self._batches.active_for(ids)
        open_alerts = await self._alerts.count_unresolved(ids)
        return [
            TankOverview(
                tank=t,
                latest=latest.get(t.id, {}),
                active_batch=active.get(t.id),
                open_alerts=open_alerts.get(t.id, 0),
            )
            for t in tanks
        ]
