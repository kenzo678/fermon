"""Fault injection driven by an injected random source (seedable, deterministic)."""

import random
from dataclasses import dataclass, field

# Values outside the backend's physical limits (-20..100 C, 0..10 bar, 0..20 %ABV).
SPIKE_VALUES: dict[str, float] = {"temperature": 150.0, "pressure": 25.0, "alcohol": 50.0}


@dataclass(frozen=True)
class FaultConfig:
    temperature_noise_std: float = 0.1
    pressure_noise_std: float = 0.01
    abv_noise_std: float = 0.05
    dropout_rate: float = 0.02
    spike_rate: float = 0.01
    disconnect_rate: float = 0.005
    disconnect_ticks: int = 5

    def __post_init__(self) -> None:
        for name in ("dropout_rate", "spike_rate", "disconnect_rate"):
            if not 0.0 <= getattr(self, name) <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.disconnect_ticks < 1:
            raise ValueError("disconnect_ticks must be >= 1")

    def noise_std(self, measurement: str) -> float:
        return {
            "temperature": self.temperature_noise_std,
            "pressure": self.pressure_noise_std,
            "alcohol": self.abv_noise_std,
        }[measurement]


@dataclass
class FaultInjector:
    config: FaultConfig
    rng: random.Random
    _offline_ticks: dict[str, int] = field(default_factory=dict)

    def begin_tick(self, device: str) -> bool:
        """Return True if the device is online for this tick (handles disconnect windows)."""
        remaining = self._offline_ticks.get(device, 0)
        if remaining > 0:
            self._offline_ticks[device] = remaining - 1
            return False
        if self.rng.random() < self.config.disconnect_rate:
            self._offline_ticks[device] = self.config.disconnect_ticks - 1
            return False
        return True

    def apply(self, measurement: str, value: float) -> float | None:
        """Return the faulty value, or None if the reading is dropped."""
        dropped = self.rng.random() < self.config.dropout_rate
        spiked = self.rng.random() < self.config.spike_rate
        noise = self.rng.gauss(0.0, self.config.noise_std(measurement))
        if dropped:
            return None
        if spiked:
            return SPIKE_VALUES[measurement]
        return value + noise
