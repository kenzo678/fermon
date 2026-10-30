from collections.abc import Sequence
from datetime import datetime

from fermon.fermentation.application.ports import ReadingRepository, TankRepository
from fermon.fermentation.domain import (
    AggregatedPoint,
    AggregationBucket,
    MeasurementType,
    TankNotFoundError,
    normalize_id,
    validate_aggregation_range,
)


class ListAggregatedReadings:
    def __init__(self, tanks: TankRepository, readings: ReadingRepository) -> None:
        self._tanks = tanks
        self._readings = readings

    async def execute(
        self,
        tank_id: str,
        bucket: AggregationBucket,
        start: datetime,
        end: datetime,
        measurements: Sequence[MeasurementType] | None = None,
    ) -> list[AggregatedPoint]:
        """Aggregated points of a tank; all measurements when none are given."""
        tank_id = normalize_id("tank_id", tank_id)
        validate_aggregation_range(start, end, bucket)
        if await self._tanks.get(tank_id) is None:
            raise TankNotFoundError(tank_id)
        wanted = list(dict.fromkeys(measurements)) if measurements else list(MeasurementType)
        return await self._readings.aggregated(tank_id, bucket, start, end, wanted)
