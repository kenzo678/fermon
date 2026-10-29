import os

import pytest
from pydantic import ValidationError

from fermon_simulator.config import Settings, TankSpec, parse_tanks


def test_parse_tanks() -> None:
    assert parse_tanks("tank-1:ale, tank-2:lager") == [
        TankSpec("tank-1", "ale"),
        TankSpec("tank-2", "lager"),
    ]


@pytest.mark.parametrize("spec", ["", "tank-1", "tank-1:stout", "a:ale,a:lager", ":ale"])
def test_parse_tanks_rejects_invalid(spec: str) -> None:
    with pytest.raises(ValueError):
        parse_tanks(spec)


def test_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in [k for k in os.environ if k.startswith("SIM_")]:
        monkeypatch.delenv(key)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.mqtt_host == "localhost"
    assert settings.mqtt_port == 1883
    assert settings.acceleration == 600
    assert settings.seed is None
    assert [t.tank_id for t in settings.tank_specs] == ["tank-1", "tank-2"]


def test_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIM_TANKS", "x:lager")
    monkeypatch.setenv("SIM_MQTT_HOST", "mosquitto")
    monkeypatch.setenv("SIM_SEED", "42")
    monkeypatch.setenv("SIM_DROPOUT_RATE", "0.5")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.tank_specs == [TankSpec("x", "lager")]
    assert settings.mqtt_host == "mosquitto"
    assert settings.seed == 42
    assert settings.fault_config().dropout_rate == 0.5


def test_invalid_tanks_fail_at_load(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIM_TANKS", "bad")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]
