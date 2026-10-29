"""Pure, deterministic fermentation model as a function of elapsed fermentation time."""

import math
from dataclasses import dataclass

_STEEPNESS = 12.0  # logistic width in units of 1/duration: ~0.25% to ~99.75% over the phase
_REST_PRESSURE_BAR = 0.05
_DAILY_DRIFT_C = 0.15


@dataclass(frozen=True)
class FermentationProfile:
    target_temperature: float  # celsius
    target_abv: float  # percent ABV at the end of fermentation
    lag_hours: float  # no activity before this
    duration_hours: float  # active fermentation length after the lag
    max_pressure: float  # bar, reached at peak activity
    exotherm: float = 1.5  # celsius gained at peak activity

    def _sigmoid(self, hours: float) -> float:
        mid = self.lag_hours + self.duration_hours / 2
        k = _STEEPNESS / self.duration_hours
        return 1.0 / (1.0 + math.exp(-k * (hours - mid)))

    def _activity(self, hours: float) -> float:
        """Normalised fermentation rate in [0, 1] (derivative of the sigmoid, peak = 1)."""
        s = self._sigmoid(hours)
        return 4.0 * s * (1.0 - s)

    def alcohol(self, hours: float) -> float:
        hours = max(hours, 0.0)
        low = self._sigmoid(self.lag_hours)
        high = self._sigmoid(self.lag_hours + self.duration_hours)
        progress = (self._sigmoid(hours) - low) / (high - low)
        return self.target_abv * min(max(progress, 0.0), 1.0)

    def pressure(self, hours: float) -> float:
        hours = max(hours, 0.0)
        rest = min(_REST_PRESSURE_BAR, self.max_pressure)
        value = rest + (self.max_pressure - rest) * self._activity(hours)
        return min(max(value, 0.0), self.max_pressure)

    def temperature(self, hours: float) -> float:
        hours = max(hours, 0.0)
        drift = _DAILY_DRIFT_C * math.sin(2 * math.pi * hours / 24.0)
        return self.target_temperature + self.exotherm * self._activity(hours) + drift


PRESETS: dict[str, FermentationProfile] = {
    "ale": FermentationProfile(
        target_temperature=19.0,
        target_abv=5.0,
        lag_hours=6.0,
        duration_hours=96.0,
        max_pressure=0.8,
        exotherm=1.5,
    ),
    "lager": FermentationProfile(
        target_temperature=10.0,
        target_abv=5.2,
        lag_hours=12.0,
        duration_hours=240.0,
        max_pressure=1.0,
        exotherm=1.0,
    ),
}
