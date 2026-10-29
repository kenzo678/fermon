import math
from dataclasses import dataclass
from datetime import datetime

from fermon.fermentation.domain.errors import InvalidIdentifierError, InvalidReadingError
from fermon.fermentation.domain.identifier import normalize_id
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
        for field in ("tank_id", "sensor_id"):
            try:
                cleaned = normalize_id(field, getattr(self, field))
            except InvalidIdentifierError as error:
                raise InvalidReadingError(error.field, str(error)) from None
            object.__setattr__(self, field, cleaned)

        if not isinstance(self.measurement, MeasurementType):
            raise InvalidReadingError("measurement", "must be a MeasurementType")
        if isinstance(self.value, bool) or not isinstance(self.value, int | float):
            raise InvalidReadingError("value", "must be a real number")
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
        if not isinstance(self.recorded_at, datetime):
            raise InvalidReadingError("recorded_at", "must be a datetime")
        if self.recorded_at.tzinfo is None or self.recorded_at.utcoffset() is None:
            raise InvalidReadingError("recorded_at", "must be timezone-aware")
