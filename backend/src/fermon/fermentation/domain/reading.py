import math
from dataclasses import dataclass
from datetime import datetime

from fermon.fermentation.domain.errors import InvalidReadingError
from fermon.fermentation.domain.measurement import MeasurementType


@dataclass(frozen=True, slots=True)
class Reading:
    tank_id: str
    sensor_id: str
    measurement: MeasurementType
    value: float
    unit: str
    recorded_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "tank_id", _clean_id("tank_id", self.tank_id))
        object.__setattr__(self, "sensor_id", _clean_id("sensor_id", self.sensor_id))

        if not isinstance(self.measurement, MeasurementType):
            raise InvalidReadingError("measurement", "must be a MeasurementType")
        if not math.isfinite(self.value):
            raise InvalidReadingError("value", "must be a finite number")
        low, high = self.measurement.limits
        if not low <= self.value <= high:
            raise InvalidReadingError(
                "value", f"{self.value} is outside {low}..{high} for {self.measurement.value}"
            )
        if self.unit != self.measurement.unit:
            raise InvalidReadingError(
                "unit", f"expected '{self.measurement.unit}' for {self.measurement.value}"
            )
        if self.recorded_at.tzinfo is None or self.recorded_at.utcoffset() is None:
            raise InvalidReadingError("recorded_at", "must be timezone-aware")


def _clean_id(field: str, raw: str) -> str:
    cleaned = raw.strip()
    if not cleaned:
        raise InvalidReadingError(field, "must not be blank")
    return cleaned
