from datetime import UTC, datetime, timedelta

import pytest

from fermon_simulator.clock import SimulationClock

START = datetime(2026, 1, 1, tzinfo=UTC)


class FakeClock:
    def __init__(self) -> None:
        self.current = START

    def now(self) -> datetime:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)


def test_starts_at_zero() -> None:
    sim = SimulationClock(acceleration=600, clock=FakeClock())
    assert sim.elapsed_hours() == 0.0


def test_one_real_second_is_ten_simulated_minutes_by_default_acceleration() -> None:
    fake = FakeClock()
    sim = SimulationClock(acceleration=600, clock=fake)
    fake.advance(1)
    assert sim.elapsed_hours() == pytest.approx(10 / 60)
    fake.advance(359)
    assert sim.elapsed_hours() == pytest.approx(60.0)


def test_real_time_when_acceleration_is_one() -> None:
    fake = FakeClock()
    sim = SimulationClock(acceleration=1, clock=fake)
    fake.advance(3600)
    assert sim.elapsed_hours() == pytest.approx(1.0)


def test_now_is_real_utc_time_not_accelerated() -> None:
    fake = FakeClock()
    sim = SimulationClock(acceleration=600, clock=fake)
    fake.advance(10)
    assert sim.now() == START + timedelta(seconds=10)
    assert sim.now().tzinfo is not None


def test_acceleration_must_be_positive() -> None:
    with pytest.raises(ValueError):
        SimulationClock(acceleration=0, clock=FakeClock())
