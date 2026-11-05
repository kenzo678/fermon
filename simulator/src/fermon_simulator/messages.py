"""Build MQTT messages that follow the backend ingest contract."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

Measurement = Literal["temperature", "pressure", "alcohol"]

UNITS: dict[str, str] = {
    "temperature": "celsius",
    "pressure": "bar",
    "alcohol": "percent_abv",
}


@dataclass(frozen=True)
class Reading:
    sensor_id: str
    measurement: Measurement
    value: float
    recorded_at: datetime


DEFAULT_TOPIC_PREFIX = "fermon"


def topic_for(tank_id: str, prefix: str = DEFAULT_TOPIC_PREFIX) -> str:
    return f"{prefix}/tanks/{tank_id}/readings"


def build_message(
    tank_id: str, reading: Reading, prefix: str = DEFAULT_TOPIC_PREFIX
) -> tuple[str, bytes]:
    if reading.recorded_at.tzinfo is None:
        raise ValueError("recorded_at must be timezone-aware")
    body = {
        "sensor_id": reading.sensor_id,
        "measurement": reading.measurement,
        "value": float(reading.value),
        "unit": UNITS[reading.measurement],
        "recorded_at": reading.recorded_at.astimezone(UTC).isoformat(),
    }
    return topic_for(tank_id, prefix), json.dumps(body).encode()
