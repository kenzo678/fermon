from dataclasses import dataclass

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from fermon_simulator.faults import FaultConfig
from fermon_simulator.profiles import PRESETS


@dataclass(frozen=True)
class TankSpec:
    tank_id: str
    preset: str


def parse_tanks(spec: str) -> list[TankSpec]:
    """Parse "tank-1:ale,tank-2:lager" into tank specs."""
    tanks: list[TankSpec] = []
    for item in spec.split(","):
        tank_id, sep, preset = (part.strip() for part in item.partition(":"))
        if not sep or not tank_id:
            raise ValueError(f"invalid tank spec {item!r}, expected '<tank_id>:<preset>'")
        if preset not in PRESETS:
            raise ValueError(f"unknown preset {preset!r}, available: {sorted(PRESETS)}")
        tanks.append(TankSpec(tank_id, preset))
    ids = [t.tank_id for t in tanks]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate tank ids")
    return tanks


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SIM_")

    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    tick_interval_seconds: float = Field(default=1.0, gt=0)
    acceleration: float = Field(default=600.0, gt=0)  # 1 real second = 10 simulated minutes
    seed: int | None = None
    tanks: str = "tank-1:ale,tank-2:lager"

    temperature_noise_std: float = Field(default=0.1, ge=0)
    pressure_noise_std: float = Field(default=0.01, ge=0)
    abv_noise_std: float = Field(default=0.05, ge=0)
    dropout_rate: float = Field(default=0.02, ge=0, le=1)
    spike_rate: float = Field(default=0.01, ge=0, le=1)
    disconnect_rate: float = Field(default=0.005, ge=0, le=1)
    disconnect_ticks: int = Field(default=5, ge=1)

    @field_validator("seed", mode="before")
    @classmethod
    def _empty_seed_is_none(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("tanks")
    @classmethod
    def _validate_tanks(cls, value: str) -> str:
        parse_tanks(value)
        return value

    @property
    def tank_specs(self) -> list[TankSpec]:
        return parse_tanks(self.tanks)

    def fault_config(self) -> FaultConfig:
        return FaultConfig(
            temperature_noise_std=self.temperature_noise_std,
            pressure_noise_std=self.pressure_noise_std,
            abv_noise_std=self.abv_noise_std,
            dropout_rate=self.dropout_rate,
            spike_rate=self.spike_rate,
            disconnect_rate=self.disconnect_rate,
            disconnect_ticks=self.disconnect_ticks,
        )
