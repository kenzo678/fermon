from dataclasses import dataclass

from fermon.fermentation.domain import Batch, MeasurementType, Reading, Tank


@dataclass(frozen=True, slots=True)
class TankOverview:
    """A tank with its latest readings, its active batch (if any) and its unresolved alert count."""

    tank: Tank
    latest: dict[MeasurementType, Reading]
    active_batch: Batch | None = None
    open_alerts: int = 0  # unresolved (open + acknowledged) alerts
