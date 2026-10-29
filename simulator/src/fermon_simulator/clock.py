"""Real clock and simulated fermentation time with an acceleration factor."""

from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class SimulationClock:
    """Fermentation time advances `acceleration` x real time; `now()` stays real UTC."""

    def __init__(self, acceleration: float, clock: Clock) -> None:
        if acceleration <= 0:
            raise ValueError("acceleration must be positive")
        self._acceleration = acceleration
        self._clock = clock
        self._start = clock.now()

    def now(self) -> datetime:
        return self._clock.now()

    def elapsed_hours(self) -> float:
        real_seconds = (self._clock.now() - self._start).total_seconds()
        return real_seconds * self._acceleration / 3600.0
