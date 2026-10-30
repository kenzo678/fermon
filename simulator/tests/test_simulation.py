import random
from datetime import UTC, datetime

from fermon_simulator.config import TankSpec
from fermon_simulator.faults import FaultConfig, FaultInjector
from fermon_simulator.simulation import generate_tick

NOW = datetime(2026, 1, 1, tzinfo=UTC)
CLEAN = FaultConfig(
    temperature_noise_std=0.0,
    pressure_noise_std=0.0,
    abv_noise_std=0.0,
    dropout_rate=0.0,
    spike_rate=0.0,
    disconnect_rate=0.0,
)


def test_three_readings_per_tank_with_sensor_ids() -> None:
    inj = FaultInjector(CLEAN, random.Random(0))
    out = generate_tick([TankSpec("tank-1", "ale"), TankSpec("tank-2", "lager")], 10.0, NOW, inj)
    assert len(out) == 6
    ids = {(tank, r.sensor_id, r.measurement) for tank, r in out if tank == "tank-1"}
    assert ids == {
        ("tank-1", "tank-1-temp", "temperature"),
        ("tank-1", "tank-1-pressure", "pressure"),
        ("tank-1", "tank-1-abv", "alcohol"),
    }
    assert all(r.recorded_at == NOW for _, r in out)


def test_offline_tank_emits_nothing() -> None:
    inj = FaultInjector(FaultConfig(disconnect_rate=1.0, disconnect_ticks=2), random.Random(0))
    assert generate_tick([TankSpec("tank-1", "ale")], 10.0, NOW, inj) == []


def test_dropout_skips_readings() -> None:
    inj = FaultInjector(FaultConfig(dropout_rate=1.0, disconnect_rate=0.0), random.Random(0))
    assert generate_tick([TankSpec("tank-1", "ale")], 10.0, NOW, inj) == []
