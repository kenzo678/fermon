from dataclasses import dataclass

from fermon.fermentation.domain import MeasurementType, Reading, Tank


@dataclass(frozen=True, slots=True)
class TankOverview:
    """A tank with its most recent reading of each measurement it has reported."""

    tank: Tank
    latest: dict[MeasurementType, Reading]
