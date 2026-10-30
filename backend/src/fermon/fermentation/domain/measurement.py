from enum import StrEnum


class MeasurementType(StrEnum):
    TEMPERATURE = "temperature"
    PRESSURE = "pressure"
    ALCOHOL = "alcohol"

    @property
    def unit(self) -> str:
        """Canonical (and only accepted) unit for this measurement."""
        return _UNITS[self]

    @property
    def limits(self) -> tuple[float, float]:
        """Inclusive plausible physical range (low, high) in the canonical unit."""
        return _LIMITS[self]


_UNITS: dict[MeasurementType, str] = {
    MeasurementType.TEMPERATURE: "celsius",
    MeasurementType.PRESSURE: "bar",
    MeasurementType.ALCOHOL: "percent_abv",
}

_LIMITS: dict[MeasurementType, tuple[float, float]] = {
    MeasurementType.TEMPERATURE: (-20.0, 100.0),
    MeasurementType.PRESSURE: (0.0, 10.0),
    MeasurementType.ALCOHOL: (0.0, 20.0),
}
