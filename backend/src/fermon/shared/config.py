import os
from pathlib import Path
from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings

_FORBIDDEN_PREFIX_CHARS = ("+", "#", "/")

# config.py -> shared -> fermon -> src -> backend (source-tree layout)
DEFAULT_ALEMBIC_INI_PATH = Path(__file__).resolve().parents[3] / "alembic.ini"


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://fermon:fermon@timescaledb:5432/fermon"
    mqtt_host: str = "mosquitto"
    mqtt_port: int = 1883
    mqtt_client_id: str = "fermon-ingestor"
    mqtt_topic_prefix: str = "fermon"
    mqtt_clean_session: bool = False
    # Where the ingestor finds Alembic's config; override when not running from the source tree.
    alembic_ini_path: Path = DEFAULT_ALEMBIC_INI_PATH

    @model_validator(mode="before")
    @classmethod
    def _reject_mqtt_topic_env(cls, data: object) -> object:
        # ``mqtt_topic`` is derived from the prefix, so a configured MQTT_TOPIC would otherwise
        # be ignored silently (pydantic-settings only reads env vars that match a field).
        if any(name.upper() == "MQTT_TOPIC" for name in os.environ):
            raise ValueError("MQTT_TOPIC is not supported; set MQTT_TOPIC_PREFIX instead")
        return data

    @model_validator(mode="after")
    def _validate_topic_prefix(self) -> Self:
        prefix = self.mqtt_topic_prefix
        if (
            not prefix
            or prefix != prefix.strip()
            or any(char in prefix for char in _FORBIDDEN_PREFIX_CHARS)
        ):
            raise ValueError(
                "MQTT_TOPIC_PREFIX must be a single non-empty topic level without "
                "'+', '#', '/' or surrounding whitespace"
            )
        return self

    @property
    def mqtt_topic(self) -> str:
        return f"{self.mqtt_topic_prefix}/tanks/+/readings"
