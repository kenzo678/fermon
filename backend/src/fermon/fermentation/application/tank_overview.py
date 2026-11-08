from dataclasses import dataclass

from fermon.fermentation.domain import Batch, MeasurementType, Reading, Tank


@dataclass(frozen=True, slots=True)
class TankOverview:
    """A tank with its latest reading of each measurement and its active batch, if any."""

    tank: Tank
    latest: dict[MeasurementType, Reading]
    active_batch: Batch | None = None
