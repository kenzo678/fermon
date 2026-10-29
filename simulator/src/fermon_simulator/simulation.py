"""One simulation tick: what every tank's sensor device would publish."""

from datetime import datetime

from fermon_simulator.config import TankSpec
from fermon_simulator.faults import FaultInjector
from fermon_simulator.messages import Measurement, Reading
from fermon_simulator.profiles import PRESETS

_SENSORS: tuple[tuple[Measurement, str], ...] = (
    ("temperature", "temp"),
    ("pressure", "pressure"),
    ("alcohol", "abv"),
)


def generate_tick(
    tanks: list[TankSpec],
    elapsed_hours: float,
    now: datetime,
    injector: FaultInjector,
) -> list[tuple[str, Reading]]:
    readings: list[tuple[str, Reading]] = []
    for tank in tanks:
        if not injector.begin_tick(tank.tank_id):
            continue
        profile = PRESETS[tank.preset]
        clean = {
            "temperature": profile.temperature(elapsed_hours),
            "pressure": profile.pressure(elapsed_hours),
            "alcohol": profile.alcohol(elapsed_hours),
        }
        for measurement, suffix in _SENSORS:
            value = injector.apply(measurement, clean[measurement])
            if value is None:
                continue
            reading = Reading(f"{tank.tank_id}-{suffix}", measurement, value, now)
            readings.append((tank.tank_id, reading))
    return readings
